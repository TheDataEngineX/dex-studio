"""Portal configuration - 45+ pre-configured company career pages."""

from __future__ import annotations

from careerdex.models.portal import ATSPlatform, PortalCompany, TitleFilter

__all__ = [
    "get_portal_config",
    "get_title_filter",
    "get_companies_by_industry",
    "get_companies_by_ats",
    "DEFAULT_COMPANIES",
]

DEFAULT_COMPANIES: list[PortalCompany] = [
    # AI Labs
    PortalCompany(
        name="OpenAI",
        slug="openai",
        careers_url="https://openai.com/careers",
        ats_platform=ATSPlatform.CUSTOM,
        industry="AI",
    ),
    PortalCompany(
        name="Anthropic",
        slug="anthropic",
        careers_url="https://anthropic.com/careers",
        ats_platform=ATSPlatform.CUSTOM,
        industry="AI",
    ),
    PortalCompany(
        name="Google DeepMind",
        slug="deepmind",
        careers_url="https://careers.google.com/locations/deepmind/",
        ats_platform=ATSPlatform.CUSTOM,
        industry="AI",
    ),
    PortalCompany(
        name="Meta AI",
        slug="meta-ai",
        careers_url="https://metacareers.com/location/menlo-park",
        ats_platform=ATSPlatform.WORKDAY,
        industry="AI",
    ),
    PortalCompany(
        name="Mistral",
        slug="mistral",
        careers_url="https://mistral.ai/careers",
        ats_platform=ATSPlatform.CUSTOM,
        industry="AI",
    ),
    PortalCompany(
        name="xAI",
        slug="xai",
        careers_url="https://x.ai/careers",
        ats_platform=ATSPlatform.CUSTOM,
        industry="AI",
    ),
    # Big Tech
    PortalCompany(
        name="Google",
        slug="google",
        careers_url="https://careers.google.com/",
        ats_platform=ATSPlatform.CUSTOM,
        industry="tech",
    ),
    PortalCompany(
        name="Microsoft",
        slug="microsoft",
        careers_url="https://careers.microsoft.com/",
        ats_platform=ATSPlatform.WORKDAY,
        industry="tech",
    ),
    PortalCompany(
        name="Amazon",
        slug="amazon",
        careers_url="https://www.amazon.jobs/",
        ats_platform=ATSPlatform.CUSTOM,
        industry="tech",
    ),
    PortalCompany(
        name="Meta",
        slug="meta",
        careers_url="https://metacareers.com/",
        ats_platform=ATSPlatform.WORKDAY,
        industry="tech",
    ),
    PortalCompany(
        name="Apple",
        slug="apple",
        careers_url="https://jobs.apple.com/",
        ats_platform=ATSPlatform.CUSTOM,
        industry="tech",
    ),
    PortalCompany(
        name="NVIDIA",
        slug="nvidia",
        careers_url="https://nvidia.wd5.myworkdayjobs.com/NVIDIA/",
        ats_platform=ATSPlatform.WORKDAY,
        industry="tech",
    ),
    # Dev Tools
    PortalCompany(
        name="GitHub",
        slug="github",
        careers_url="https://github.com/about/careers",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="devtools",
    ),
    PortalCompany(
        name="GitLab",
        slug="gitlab",
        careers_url="https://about.gitlab.com/jobs/",
        ats_platform=ATSPlatform.CUSTOM,
        industry="devtools",
    ),
    PortalCompany(
        name="Vercel",
        slug="vercel",
        careers_url="https://vercel.com/careers",
        ats_platform=ATSPlatform.ASHBY,
        industry="devtools",
    ),
    PortalCompany(
        name="Cloudflare",
        slug="cloudflare",
        careers_url="https://cloudflare.com/careers/",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="devtools",
    ),
    PortalCompany(
        name="Datadog",
        slug="datadog",
        careers_url="https://careers.datadoghq.com/",
        ats_platform=ATSPlatform.ASHBY,
        industry="devtools",
    ),
    PortalCompany(
        name="Elastic",
        slug="elastic",
        careers_url="https://www.elastic.co/careers",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="devtools",
    ),
    # Scaleups
    PortalCompany(
        name="Figma",
        slug="figma",
        careers_url="https://www.figma.com/careers/",
        ats_platform=ATSPlatform.ASHBY,
        industry="design",
    ),
    PortalCompany(
        name="Notion",
        slug="notion",
        careers_url="https://notion.com/careers",
        ats_platform=ATSPlatform.ASHBY,
        industry="productivity",
    ),
    PortalCompany(
        name="Stripe",
        slug="stripe",
        careers_url="https://stripe.com/jobs",
        ats_platform=ATSPlatform.CUSTOM,
        industry="fintech",
    ),
    PortalCompany(
        name="Airbnb",
        slug="airbnb",
        careers_url="https://airbnb.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="travel",
    ),
    PortalCompany(
        name="Uber",
        slug="uber",
        careers_url="https://uber.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="mobility",
    ),
    PortalCompany(
        name="Lyft",
        slug="lyft",
        careers_url="https://lyft.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="mobility",
    ),
    # Data & ML
    PortalCompany(
        name="Databricks",
        slug="databricks",
        careers_url="https://databricks.com/careers",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="data",
    ),
    PortalCompany(
        name="Snowflake",
        slug="snowflake",
        careers_url="https://careers.snowflake.com/",
        ats_platform=ATSPlatform.WORKDAY,
        industry="data",
    ),
    PortalCompany(
        name="MongoDB",
        slug="mongodb",
        careers_url="https://mongodb.com/careers",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="database",
    ),
    PortalCompany(
        name="Confluent",
        slug="confluent",
        careers_url="https://confluent.io/careers/",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="data",
    ),
    # Security
    PortalCompany(
        name="CrowdStrike",
        slug="crowdstrike",
        careers_url="https://crowdstrike.com/careers/",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="security",
    ),
    PortalCompany(
        name="Palo Alto Networks",
        slug="palo-alto",
        careers_url="https://paloaltonetworks.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="security",
    ),
    PortalCompany(
        name="Wiz",
        slug="wiz",
        careers_url="https://wiz.io/careers/",
        ats_platform=ATSPlatform.ASHBY,
        industry="security",
    ),
    # Infrastructure
    PortalCompany(
        name="HashiCorp",
        slug="hashicorp",
        careers_url="https://hashicorp.com/careers",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="infrastructure",
    ),
    PortalCompany(
        name="Docker",
        slug="docker",
        careers_url="https://docker.com/careers",
        ats_platform=ATSPlatform.CUSTOM,
        industry="infrastructure",
    ),
    # Cloud
    PortalCompany(
        name="DigitalOcean",
        slug="digitalocean",
        careers_url="https://digitalocean.com/careers",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="cloud",
    ),
    # Observability
    PortalCompany(
        name="Grafana Labs",
        slug="grafana",
        careers_url="https://grafana.com/about/careers/",
        ats_platform=ATSPlatform.ASHBY,
        industry="observability",
    ),
    PortalCompany(
        name="New Relic",
        slug="newrelic",
        careers_url="https://newrelic.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="observability",
    ),
    # Finance
    PortalCompany(
        name="Coinbase",
        slug="coinbase",
        careers_url="https://coinbase.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="crypto",
    ),
    PortalCompany(
        name="Robinhood",
        slug="robinhood",
        careers_url="https://robinhood.com/careers/",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="fintech",
    ),
    # Other Tech
    PortalCompany(
        name="Spotify",
        slug="spotify",
        careers_url="https://spotify.com/careers",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="media",
    ),
    PortalCompany(
        name="Discord",
        slug="discord",
        careers_url="https://discord.com/careers",
        ats_platform=ATSPlatform.ASHBY,
        industry="social",
    ),
    PortalCompany(
        name="Slack",
        slug="slack",
        careers_url="https://slack.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="productivity",
    ),
    PortalCompany(
        name="Zoom",
        slug="zoom",
        careers_url="https://zoom.us/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="communications",
    ),
    PortalCompany(
        name="Atlassian",
        slug="atlassian",
        careers_url="https://atlassian.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="productivity",
    ),
    PortalCompany(
        name="Salesforce",
        slug="salesforce",
        careers_url="https://salesforce.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="crm",
    ),
    PortalCompany(
        name="ServiceNow",
        slug="servicenow",
        careers_url="https://servicenow.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="enterprise",
    ),
    PortalCompany(
        name="Workday",
        slug="workday",
        careers_url="https://workday.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="enterprise",
    ),
    PortalCompany(
        name="Intuit",
        slug="intuit",
        careers_url="https://intuit.com/careers/",
        ats_platform=ATSPlatform.WORKDAY,
        industry="fintech",
    ),
    PortalCompany(
        name="DocuSign",
        slug="docusign",
        careers_url="https://docusign.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="productivity",
    ),
    PortalCompany(
        name="Box",
        slug="box",
        careers_url="https://box.com/careers",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="storage",
    ),
    PortalCompany(
        name="Square",
        slug="square",
        careers_url="https://squareup.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="fintech",
    ),
    PortalCompany(
        name="DoorDash",
        slug="doordash",
        careers_url="https://doordash.com/careers",
        ats_platform=ATSPlatform.WORKDAY,
        industry="delivery",
    ),
    PortalCompany(
        name="Instacart",
        slug="instacart",
        careers_url="https://instacart.com/careers/",
        ats_platform=ATSPlatform.GREENHOUSE,
        industry="retail",
    ),
]


def get_portal_config() -> list[PortalCompany]:
    """Get list of configured portal companies."""
    return [c for c in DEFAULT_COMPANIES if c.enabled]


def get_title_filter() -> TitleFilter:
    """Get default title filter."""
    return TitleFilter()


def get_companies_by_industry(industry: str) -> list[PortalCompany]:
    """Get companies filtered by industry."""
    return [c for c in DEFAULT_COMPANIES if c.industry == industry and c.enabled]


def get_companies_by_ats(platform: ATSPlatform) -> list[PortalCompany]:
    """Get companies filtered by ATS platform."""
    return [c for c in DEFAULT_COMPANIES if c.ats_platform == platform and c.enabled]
