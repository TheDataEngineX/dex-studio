"""Email client — IMAP-based email fetching, parsing, and job-matching.

Connects to any IMAP server (Gmail, Outlook, Yahoo, self-hosted).
Scans inbox for job-related emails and matches them to tracked applications.
"""

from __future__ import annotations

import contextlib
import email
import email.header
import email.utils
import imaplib
import re
import ssl
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from careerdex.models.email import (
    EmailCategory,
    EmailConfig,
    EmailMatchResult,
    EmailMessage,
)

if TYPE_CHECKING:
    from careerdex.models.application import ApplicationEntry

logger = structlog.get_logger()

__all__ = ["EmailClient"]

# Patterns for categorising job-related emails
_CATEGORY_PATTERNS: dict[EmailCategory, list[re.Pattern[str]]] = {
    EmailCategory.APPLICATION_CONFIRMATION: [
        re.compile(r"application\s+(received|confirmed|submitted)", re.IGNORECASE),
        re.compile(r"thank\s+you\s+for\s+(applying|your\s+application)", re.IGNORECASE),
        re.compile(r"we\s+received\s+your\s+application", re.IGNORECASE),
    ],
    EmailCategory.RECRUITER_OUTREACH: [
        re.compile(r"(exciting|great)\s+opportunity", re.IGNORECASE),
        re.compile(r"i\s+came\s+across\s+your\s+profile", re.IGNORECASE),
        re.compile(r"(interested\s+in|consider)\s+(this\s+)?role", re.IGNORECASE),
        re.compile(r"i('m|\s+am)\s+a\s+recruiter", re.IGNORECASE),
        re.compile(r"reaching\s+out\s+(about|regarding)", re.IGNORECASE),
    ],
    EmailCategory.INTERVIEW_INVITE: [
        re.compile(r"(schedule|book|set\s+up)\s+(a\s+|an\s+)?(interview|call|chat)", re.IGNORECASE),
        re.compile(r"(interview|screen)\s+(invitation|request|schedule)", re.IGNORECASE),
        re.compile(r"like\s+to\s+(meet|speak|chat)\s+with\s+you", re.IGNORECASE),
        re.compile(r"next\s+step", re.IGNORECASE),
    ],
    EmailCategory.REJECTION: [
        re.compile(r"(unfortunately|regret)\s+.{0,40}(not|unable|won't)", re.IGNORECASE),
        re.compile(r"decided\s+(to\s+)?(not\s+)?(move|proceed)\s+forward", re.IGNORECASE),
        re.compile(r"position\s+has\s+been\s+filled", re.IGNORECASE),
        re.compile(r"other\s+candidates?\s+.{0,20}(better|more\s+closely)", re.IGNORECASE),
    ],
    EmailCategory.OFFER: [
        re.compile(r"(pleased|happy|excited)\s+to\s+offer", re.IGNORECASE),
        re.compile(r"(offer\s+letter|job\s+offer|employment\s+offer)", re.IGNORECASE),
        re.compile(r"extend\s+(an\s+)?offer", re.IGNORECASE),
    ],
    EmailCategory.FOLLOW_UP: [
        re.compile(r"follow(ing)?\s+up", re.IGNORECASE),
        re.compile(r"checking\s+in", re.IGNORECASE),
        re.compile(r"any\s+update", re.IGNORECASE),
    ],
    EmailCategory.STATUS_UPDATE: [
        re.compile(r"(application|status)\s+update", re.IGNORECASE),
        re.compile(r"update\s+on\s+your\s+application", re.IGNORECASE),
        re.compile(r"moving\s+(you\s+)?(to\s+the\s+)?next\s+(stage|round|step)", re.IGNORECASE),
    ],
    EmailCategory.NETWORKING: [
        re.compile(r"connect\s+on\s+linkedin", re.IGNORECASE),
        re.compile(r"(referral|refer)\s+(you|your)", re.IGNORECASE),
        re.compile(r"networking", re.IGNORECASE),
    ],
}

# Known job-board and recruiter domains
_JOB_DOMAINS: set[str] = {
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "lever.co",
    "greenhouse.io",
    "workday.com",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "ashbyhq.com",
    "dover.com",
    "gem.com",
    "hired.com",
    "dice.com",
    "monster.com",
    "angel.co",
    "wellfound.com",
    "remotive.com",
    "weworkremotely.com",
}


class EmailClient:
    """IMAP email client for job email scanning.

    Usage::

        client = EmailClient(config)
        client.connect()
        emails = client.fetch_job_emails()
        matches = client.match_to_applications(emails, applications)
        client.disconnect()
    """

    def __init__(self, config: EmailConfig) -> None:
        self.config = config
        self._conn: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None

    def connect(self) -> None:
        """Establish IMAP connection."""
        try:
            if self.config.use_ssl:
                ctx = ssl.create_default_context()
                self._conn = imaplib.IMAP4_SSL(
                    self.config.host,
                    self.config.port,
                    ssl_context=ctx,
                )
            else:
                self._conn = imaplib.IMAP4(self.config.host, self.config.port)
            self._conn.login(self.config.username, self.config.password)
            logger.info("imap_connected", host=self.config.host, user=self.config.username)
        except imaplib.IMAP4.error as exc:
            logger.error("imap_connection_failed", host=self.config.host, error=str(exc))
            raise

    def disconnect(self) -> None:
        """Close IMAP connection."""
        if self._conn is not None:
            with contextlib.suppress(imaplib.IMAP4.error):
                self._conn.close()
            with contextlib.suppress(imaplib.IMAP4.error):
                self._conn.logout()
            self._conn = None

    def fetch_job_emails(self) -> list[EmailMessage]:
        """Fetch and parse emails from configured folders.

        Filters by date range and scans for job-related content.
        Returns parsed EmailMessage objects with category classification.
        """
        if self._conn is None:
            msg = "Not connected — call connect() first"
            raise RuntimeError(msg)

        since_date = datetime.now(UTC) - timedelta(days=self.config.days_back)
        since_str = since_date.strftime("%d-%b-%Y")
        all_emails: list[EmailMessage] = []

        for folder in self.config.folders:
            try:
                status, _ = self._conn.select(folder, readonly=True)
                if status != "OK":
                    logger.warning("imap_folder_select_failed", folder=folder)
                    continue

                # Search for emails since the configured date
                _, msg_nums = self._conn.search(None, f'(SINCE "{since_str}")')
                if not msg_nums or not msg_nums[0]:
                    continue

                ids = msg_nums[0].split()
                # Take most recent N emails
                ids = ids[-self.config.max_fetch :]

                for msg_id in ids:
                    parsed = self._fetch_and_parse(msg_id, folder)
                    if parsed is not None and self._is_job_related(parsed):
                        all_emails.append(parsed)

            except imaplib.IMAP4.error:
                logger.warning("imap_folder_error", folder=folder)
                continue

        logger.info("email_scan_complete", total=len(all_emails))
        return all_emails

    def match_to_applications(
        self,
        emails: list[EmailMessage],
        applications: list[ApplicationEntry],
    ) -> list[EmailMatchResult]:
        """Match emails to tracked applications by company/position similarity."""
        results: list[EmailMatchResult] = []

        for msg in emails:
            best_match: EmailMatchResult | None = None
            best_score = 0.0

            for app in applications:
                score, reason = self._compute_match(msg, app)
                if score > best_score and score >= 0.3:
                    best_score = score
                    best_match = EmailMatchResult(
                        email_id=msg.id,
                        application_id=app.id,
                        confidence=score,
                        match_reason=reason,
                    )

            if best_match is not None:
                results.append(best_match)

        return results

    # -- private helpers --------------------------------------------------

    def _fetch_and_parse(
        self,
        msg_id: bytes,
        folder: str,
    ) -> EmailMessage | None:
        """Fetch a single email and parse it into an EmailMessage."""
        if self._conn is None:
            return None
        try:
            _, data = self._conn.fetch(msg_id.decode(), "(RFC822 FLAGS)")
            if not data or not data[0] or not isinstance(data[0], tuple):
                return None

            raw = data[0][1]
            if not isinstance(raw, bytes):
                return None

            msg = email.message_from_bytes(raw)

            subject = self._decode_header(msg.get("Subject", ""))
            sender = msg.get("From", "")
            sender_name, sender_addr = email.utils.parseaddr(sender)
            date_str = msg.get("Date", "")
            date = email.utils.parsedate_to_datetime(date_str) if date_str else datetime.now(UTC)
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            message_id = msg.get("Message-ID", "")
            recipients = [
                addr
                for _, addr in email.utils.getaddresses(
                    msg.get_all("To", []) + msg.get_all("Cc", [])
                )
            ]

            # Extract flags
            flags_data = data[0][0] if isinstance(data[0][0], bytes) else b""
            is_read = b"\\Seen" in flags_data

            body_text, body_html = self._extract_body(msg)

            parsed = EmailMessage(
                message_id=message_id,
                subject=subject,
                sender=sender_addr,
                sender_name=self._decode_header(sender_name),
                recipients=recipients,
                date=date,
                body_text=body_text,
                body_html=body_html,
                folder=folder,
                is_read=is_read,
            )

            # Classify and extract
            parsed.category = self._categorise(parsed)
            parsed.extracted_company = self._extract_company(parsed)
            parsed.extracted_position = self._extract_position(parsed)
            parsed.keywords_found = self._extract_keywords(parsed)

            return parsed

        except Exception:
            logger.debug("email_parse_failed", msg_id=msg_id)
            return None

    def _extract_body(self, msg: email.message.Message) -> tuple[str, str]:  # noqa: C901
        """Extract plain text and HTML body from an email."""
        text = ""
        html = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in disposition:
                    continue
                payload = part.get_payload(decode=True)
                if not isinstance(payload, bytes):
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if content_type == "text/plain" and not text:
                    text = decoded
                elif content_type == "text/html" and not html:
                    html = decoded
        else:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html = decoded
                else:
                    text = decoded

        return text, html

    def _decode_header(self, value: str) -> str:
        """Decode RFC 2047 encoded header value."""
        if not value:
            return ""
        parts = email.header.decode_header(value)
        decoded: list[str] = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)

    def _is_job_related(self, msg: EmailMessage) -> bool:
        """Check if an email is likely job-related."""
        # Check sender domain
        sender_domain = msg.sender.split("@")[-1] if "@" in msg.sender else ""
        if any(domain in sender_domain for domain in _JOB_DOMAINS):
            return True

        # Check for job keywords in subject + body
        combined = f"{msg.subject} {msg.body_text[:2000]}".lower()
        job_keywords = {
            "job",
            "position",
            "role",
            "opportunity",
            "application",
            "interview",
            "hiring",
            "recruit",
            "candidate",
            "resume",
            "salary",
            "offer letter",
            "onboarding",
        }
        return sum(1 for kw in job_keywords if kw in combined) >= 2

    def _categorise(self, msg: EmailMessage) -> EmailCategory:
        """Classify an email into a job-related category."""
        combined = f"{msg.subject} {msg.body_text[:3000]}"
        for category, patterns in _CATEGORY_PATTERNS.items():
            if any(p.search(combined) for p in patterns):
                return category
        return EmailCategory.UNKNOWN

    def _extract_company(self, msg: EmailMessage) -> str:
        """Best-effort company name extraction from sender."""
        # Try sender name first (e.g. "Google Recruiting")
        if msg.sender_name:
            # Remove common suffixes
            name = re.sub(
                r"\s*(recruiting|talent|careers?|hr|hiring|team|jobs?)$",
                "",
                msg.sender_name,
                flags=re.IGNORECASE,
            ).strip()
            if name and len(name) > 1:
                return name

        # Fall back to sender domain
        if "@" in msg.sender:
            domain = msg.sender.split("@")[-1]
            # Skip generic email providers
            generic = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"}
            if domain not in generic and domain not in _JOB_DOMAINS:
                return domain.split(".")[0].title()

        return ""

    def _extract_position(self, msg: EmailMessage) -> str:
        """Best-effort position title extraction from subject/body."""
        combined = f"{msg.subject}\n{msg.body_text[:2000]}"

        # Pattern: "for the <TITLE> position/role"
        match = re.search(
            r"for\s+the\s+(.{3,60}?)\s+(position|role|opening)",
            combined,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

        # Pattern: "regarding the <TITLE>"
        match = re.search(
            r"regarding\s+the\s+(.{3,60}?)\s+(position|role|opportunity)",
            combined,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

        # Pattern: "<TITLE> at <COMPANY>"
        match = re.search(
            r"([\w\s/]+(?:engineer|developer|manager|analyst|scientist|designer|architect|lead|director|coordinator|specialist|consultant))\s+at\s+",
            combined,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()

        return ""

    def _extract_keywords(self, msg: EmailMessage) -> list[str]:
        """Extract job-related keywords found in the email."""
        combined = f"{msg.subject} {msg.body_text[:3000]}".lower()
        keywords = [
            "interview",
            "offer",
            "application",
            "salary",
            "remote",
            "onsite",
            "hybrid",
            "recruiter",
            "hiring manager",
            "next steps",
            "technical assessment",
            "coding challenge",
            "phone screen",
            "background check",
            "start date",
            "compensation",
        ]
        return [kw for kw in keywords if kw in combined]

    def _compute_match(  # noqa: C901
        self,
        msg: EmailMessage,
        app: ApplicationEntry,
    ) -> tuple[float, str]:
        """Compute a match score between an email and a tracked application."""
        score = 0.0
        reasons: list[str] = []

        # Company name match (strongest signal)
        if app.company and msg.extracted_company:
            company_a = app.company.lower().strip()
            company_b = msg.extracted_company.lower().strip()
            if company_a == company_b or company_a in company_b or company_b in company_a:
                score += 0.5
                reasons.append("company name match")

        # Sender domain contains company name
        if app.company and "@" in msg.sender:
            domain = msg.sender.split("@")[-1].lower()
            company_slug = re.sub(r"[^a-z0-9]", "", app.company.lower())
            if company_slug and company_slug in domain:
                score += 0.3
                reasons.append("sender domain match")

        # Position title match
        if app.position and msg.extracted_position:
            pos_a = app.position.lower()
            pos_b = msg.extracted_position.lower()
            if pos_a == pos_b:
                score += 0.3
                reasons.append("exact position match")
            elif pos_a in pos_b or pos_b in pos_a:
                score += 0.15
                reasons.append("partial position match")

        # Contact email match
        if app.contact_email and app.contact_email.lower() == msg.sender.lower():
            score += 0.4
            reasons.append("contact email match")

        return min(score, 1.0), " + ".join(reasons) if reasons else "no match"
