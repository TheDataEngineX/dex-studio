"""Negotiation service - generates salary negotiation scripts."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "NegotiationScript",
    "generate_negotiation_script",
]


@dataclass
class OfferDetails:
    """Offer details from company."""

    base_salary: float
    equity: float = 0
    equity_years: int = 4
    signing_bonus: float = 0
    annual_bonus: float = 0
    benefits: str = ""
    company: str = ""
    role: str = ""


@dataclass
class MarketData:
    """Market compensation data."""

    min_salary: float
    median_salary: float
    max_salary: float
    equity_median: float
    sources: list[str]


class NegotiationScript:
    """Generated negotiation script."""

    def __init__(
        self,
        offer: OfferDetails,
        target_salary: float,
        market_data: MarketData,
        opening_script: str,
        salary_talking_points: list[str],
        equity_talking_points: list[str],
        email_template: str,
        counter_offer_strategy: str,
    ):
        self.offer = offer
        self.target_salary = target_salary
        self.market_data = market_data
        self.opening_script = opening_script
        self.salary_talking_points = salary_talking_points
        self.equity_talking_points = equity_talking_points
        self.email_template = email_template
        self.counter_offer_strategy = counter_offer_strategy


class NegotiationService:
    """Service for generating negotiation scripts."""

    def __init__(self) -> None:
        self.default_templates = {
            "en": {
                "opening": (
                    "Thank you so much for the offer! I'm genuinely excited about "
                    "the opportunity to join {company} as {role}. "
                    "Before we discuss the details, I want to express my enthusiasm "
                    "for the team's mission and the technical challenges ahead."
                ),
                "email_thank_you": (
                    "Subject: Re: Offer from {company} - Next Steps\n\n"
                    "Hi {recruiter_name},\n\n"
                    "Thank you so much for the offer! I'm excited about the opportunity.\n\n"
                    "I've reviewed the package carefully and would like to discuss "
                    "some aspects. Can we schedule a call to talk through it?\n\n"
                    "I'm very enthusiastic about joining {company} and believe "
                    "we can find terms that work for everyone.\n\n"
                    "Best regards,\n{your_name}"
                ),
            },
        }

    def generate(
        self,
        offer: OfferDetails,
        target_salary: float | None = None,
        market_data: MarketData | None = None,
    ) -> NegotiationScript:
        """Generate a personalized negotiation script."""

        if target_salary is None:
            target_salary = offer.base_salary * 1.15

        if market_data is None:
            market_data = self._get_default_market_data()

        template = self.default_templates.get("en", self.default_templates["en"])

        opening_script = template["opening"].format(
            company=offer.company,
            role=offer.role,
        )

        salary_talking_points = self._generate_salary_points(offer, target_salary, market_data)

        equity_talking_points = self._generate_equity_points(offer, market_data)

        email_template = self._generate_email_template(offer, template, target_salary)

        counter_strategy = self._generate_counter_strategy(offer, target_salary, market_data)

        return NegotiationScript(
            offer=offer,
            target_salary=target_salary,
            market_data=market_data,
            opening_script=opening_script,
            salary_talking_points=salary_talking_points,
            equity_talking_points=equity_talking_points,
            email_template=email_template,
            counter_offer_strategy=counter_strategy,
        )

    def _get_default_market_data(self) -> MarketData:
        """Get default market data."""
        return MarketData(
            min_salary=120000,
            median_salary=180000,
            max_salary=250000,
            equity_median=0.1,
            sources=["levels.fyi", "glassdoor", "blind"],
        )

    def _generate_salary_points(
        self,
        offer: OfferDetails,
        target: float,
        market: MarketData,
    ) -> list[str]:
        """Generate salary negotiation talking points."""
        points = []

        if offer.base_salary < market.median_salary:
            points.append(
                f"The median for this role is ${market.median_salary:,.0f}. "
                "My target reflects the upper range of market compensation."
            )

        if target > offer.base_salary:
            diff = target - offer.base_salary
            points.append(
                f"I'm requesting ${diff:,.0f} more than the initial offer, "
                f"which represents {diff / offer.base_salary * 100:.0f}% increase. "
                "This is justified by my experience and current market conditions."
            )

        points.append(
            "I've received another offer at a higher comp, which helps "
            "inform my expectations (if applicable)."
        )

        points.append(
            "I'm flexible and want to find a package that works for both of us. "
            "Non-salary components can also be part of the discussion."
        )

        return points

    def _generate_equity_points(
        self,
        offer: OfferDetails,
        market: MarketData,
    ) -> list[str]:
        """Generate equity negotiation talking points."""
        points = []

        if offer.equity < market.equity_median:
            points.append(
                f"Standard equity for this level is around {market.equity_median * 100:.1f}% "
                "I'd like to discuss aligning closer to market."
            )

        points.append(
            "I'd appreciate clarity on the strike price and current valuation, "
            "as that impacts the actual value of the equity package."
        )

        points.append(
            "Can we discuss acceleration on vesting? A one-year acceleration "
            "would provide additional alignment with company success."
        )

        return points

    def _generate_email_template(
        self,
        offer: OfferDetails,
        template: dict[str, str],
        target_salary: float,
    ) -> str:
        """Generate email template."""
        return template["email_thank_you"].format(
            company=offer.company,
            recruiter_name="[Recruiter Name]",
            your_name="[Your Name]",
        )

    def _generate_counter_strategy(
        self,
        offer: OfferDetails,
        target: float,
        market: MarketData,
    ) -> str:
        """Generate counter-offer strategy."""
        if target <= offer.base_salary:
            return (
                "The initial offer is already competitive. Focus on "
                "non-salary components: signing bonus, equity, or PTO."
            )

        strategy = [
            f"Counter at ${target:,.0f} (vs ${offer.base_salary:,.0f} offer)",
            f"Gap to close: ${target - offer.base_salary:,.0f}",
            "",
            "If they can't meet salary target:",
            f"  - Request signing bonus: ${int((target - offer.base_salary) * 0.5):,}",
            f"  - Request additional equity: +{int(offer.equity * 0.25 * 10000):,} shares",
            "  - Ask about accelerated vesting",
            "",
            f"Walk-away point: Based on market data, don't go below ${market.min_salary:,.0f}.",
        ]

        return "\n".join(strategy)


def generate_negotiation_script(
    base_salary: float,
    company: str = "",
    role: str = "",
    equity: float = 0,
    target_salary: float | None = None,
) -> NegotiationScript:
    """Convenience function to generate negotiation script."""
    offer = OfferDetails(
        base_salary=base_salary,
        equity=equity,
        company=company,
        role=role,
    )
    service = NegotiationService()
    return service.generate(offer, target_salary)
