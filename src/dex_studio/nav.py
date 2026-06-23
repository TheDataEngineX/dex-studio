"""Navigation structure — single source of truth for sidebar, breadcrumbs, and command palette.

Add/remove/rename nav items here; sidebar, breadcrumbs, and ⌘K all update automatically.
"""

from __future__ import annotations

from typing import Any


def _item(
    label: str,
    href: str,
    icon: str,
    sub: str = "",
    *,
    exact: bool = False,
    badge: str = "",
    badge_color: str = "accent",
) -> dict[str, Any]:
    d: dict[str, Any] = {"label": label, "href": href, "icon": icon, "sub": sub}
    if exact:
        d["exact"] = True
    if badge:
        d["badge"] = badge
        d["badge_color"] = badge_color
    return d


NAV_GROUPS: list[dict[str, Any]] = [
    {
        "label": None,
        "id": "home",
        "items": [
            _item("Home", "/", "home", "Project overview & recent activity", exact=True),
        ],
    },
    {
        "label": "Data",
        "id": "data",
        "items": [
            _item("Sources", "/data/sources", "link", "Connectors and ingest configs"),
            _item("Catalog", "/data/catalog", "table-2", "Browse bronze / silver / gold"),
            _item("Warehouse", "/data/warehouse", "database", "Gold layer — BI-ready tables"),
            _item("SQL", "/data/sql", "hash", "Ad-hoc query editor"),
            _item("Lineage", "/data/lineage", "share-2", "Trace data flow end-to-end"),
            _item("Quality", "/data/quality", "shield-check", "Quality tests and scores"),
            _item("Schema", "/data/schema", "file-code", "Contracts and drift detection"),
        ],
    },
    {
        "label": "Pipelines",
        "id": "pipelines",
        "items": [
            _item("Pipelines", "/data/pipelines", "workflow", "DAG runner — bronze → gold"),
            _item("Transforms", "/data/transforms", "code-2", "SQL + Python transforms"),
            _item("Streaming", "/data/streaming", "radio", "SSE / Kafka consumers"),
            _item("Watermarks", "/data/watermarks", "droplets", "Ingestion cursors / dedup state"),
            _item("Backfill", "/data/backfill", "rewind", "Reset watermarks and re-ingest"),
            _item("Scheduler", "/system/scheduler", "clock", "Cron schedules + DAG triggers"),
            _item("Runs", "/system/runs", "list", "Unified run history"),
        ],
    },
    {
        "label": "Intelligence",
        "id": "intelligence",
        "items": [
            _item(
                "Playground",
                "/intelligence/playground",
                "message-square",
                "Chat over your data",
                badge="live",
                badge_color="green",
            ),
            _item("Models", "/intelligence/models", "box", "Model registry and deployment"),
            _item(
                "Experiments",
                "/intelligence/experiments",
                "flask-conical",
                "Track and compare ML runs",
            ),
            _item("Features", "/intelligence/features", "layers", "Feature store and groups"),
            _item(
                "Predictions", "/intelligence/predictions", "zap", "Run inference against models"
            ),
            _item("Drift", "/intelligence/drift", "activity", "Model drift monitoring"),
            _item("Agents", "/intelligence/agents", "bot", "Autonomous AI agents"),
            _item("Tools", "/intelligence/tools", "wrench", "Tool catalog (3-tier registry)"),
            _item("Traces", "/intelligence/traces", "git-branch", "Agent execution traces"),
            _item("Embeddings", "/intelligence/embeddings", "layers", "Embedding collections"),
            _item(
                "Fine-tune",
                "/intelligence/finetune",
                "flask-conical",
                "Train models on lakehouse data",
            ),
        ],
    },
    {
        "label": "Platform",
        "id": "platform",
        "items": [
            _item("Privacy", "/secops", "shield", "PrivacyGuard — PII protection"),
            _item("Audit log", "/secops/audit", "file-text", "Immutable event record"),
            _item("Compaction", "/system/compaction", "archive", "Merge small parquet files"),
            _item("Alerting", "/system/alerting", "bell", "Webhook alerts and SLA"),
            _item("Logs", "/system/logs", "scroll", "Structured log viewer"),
            _item("Status", "/system/status", "activity", "Component health"),
            _item("Components", "/system/components", "cpu", "Engine internals"),
            _item("Settings", "/system/settings", "sliders", "dex.yaml configuration"),
            _item("Costs", "/system/costs", "bar-chart-2", "API spend tracking"),
        ],
    },
]


def _item_matches(item: dict[str, Any], path: str) -> bool:
    href: str = item["href"]
    if item.get("exact"):
        return path == href
    return path == href or (href != "/" and path.startswith(href))


def _domain_fallback(path: str) -> list[tuple[str, str | None]]:
    path_with_slash = path.rstrip("/") + "/"
    for dom in NAV_DOMAINS:
        prefix = str(dom.get("prefix", ""))
        if prefix and (path.startswith(prefix) or path_with_slash == prefix):
            return [(str(dom["label"]), None)]
    return [("Home", "/")]


def breadcrumbs(path: str) -> list[tuple[str, str | None]]:
    """Derive breadcrumb trail from the current path.

    Returns a list of (label, href_or_None). The last entry has href=None
    (it's the current page, not a link).
    """
    if path in ("/", ""):
        return [("Home", None)]

    best_item: dict[str, Any] | None = None
    best_group: dict[str, Any] | None = None
    best_len = 0

    for group in NAV_GROUPS:
        for item in group["items"]:
            if _item_matches(item, path) and len(item["href"]) > best_len:
                best_item = item
                best_group = group
                best_len = len(item["href"])

    if not best_item or not best_group:
        return _domain_fallback(path)

    crumbs: list[tuple[str, str | None]] = []
    group_label = best_group["label"]
    # Suppress group crumb when it duplicates the item label (e.g. "Pipelines > Pipelines")
    if group_label and group_label != best_item["label"]:
        crumbs.append((group_label, None))
    leaf_href = best_item["href"] if path != best_item["href"] else None
    crumbs.append((best_item["label"], leaf_href))
    return crumbs


def active_group_id(path: str) -> str:
    """Return the id of the nav group that owns the current path."""
    if path in ("/", ""):
        return "home"

    best_id = ""
    best_len = 0

    for group in NAV_GROUPS:
        for item in group["items"]:
            href: str = item["href"]
            matches = (
                path == href
                if item.get("exact")
                else (path == href or (href != "/" and path.startswith(href)))
            )
            if matches and len(href) > best_len:
                best_id = group["id"]
                best_len = len(href)

    return best_id


def cmd_palette_pages() -> list[dict[str, str]]:
    """Flat list of all nav items, shaped for the command palette JS."""
    return [
        {
            "g": group["label"] or "Home",
            "icon": item["icon"],
            "label": item["label"],
            "sub": item.get("sub", ""),
            "href": item["href"],
        }
        for group in NAV_GROUPS
        for item in group["items"]
    ]


# ── Two-rail domain structure ────────────────────────────────────────────────
# Each domain maps to one icon in the 44px rail.
# page_groups mirrors spec §3.3 Monitor · Explore · Build.

_D = _item  # alias for readability in this section

NAV_DOMAINS: list[dict[str, Any]] = [
    {
        "id": "data",
        "label": "Data",
        "icon": "database",
        "color": "#60a5fa",
        "href": "/data/pipelines",
        "prefix": "/data/",
        "page_groups": [
            {
                "label": "Monitor",
                "items": [
                    _D(
                        "Dashboard",
                        "/data/dashboard",
                        "layout-dashboard",
                        "Pipeline health at a glance",
                    ),
                    _D("Pipelines", "/data/pipelines", "workflow", "DAG runner — bronze → gold"),
                    _D(
                        "Watermarks",
                        "/data/watermarks",
                        "droplets",
                        "Ingestion cursors and dedup state",
                    ),
                ],
            },
            {
                "label": "Explore",
                "items": [
                    _D("Sources", "/data/sources", "link", "Connectors and ingest configs"),
                    _D("Catalog", "/data/catalog", "table-2", "Browse bronze / silver / gold"),
                    _D("SQL", "/data/sql", "hash", "Ad-hoc query editor"),
                ],
            },
            {
                "label": "Build",
                "items": [
                    _D("Backfill", "/data/backfill", "rewind", "Reset watermarks and re-ingest"),
                    _D("Schema", "/data/schema", "file-code", "Contracts and drift detection"),
                ],
            },
        ],
    },
    {
        "id": "intelligence",
        "label": "Intelligence",
        "icon": "sparkles",
        "color": "#a78bfa",
        "href": "/intelligence/playground",
        "prefix": "/intelligence/",
        "page_groups": [
            {
                "label": "Monitor",
                "items": [
                    _D(
                        "Dashboard",
                        "/intelligence/dashboard",
                        "layout-dashboard",
                        "Unified ML + AI health overview",
                    ),
                    _D("Models", "/intelligence/models", "box", "Model registry and deployment"),
                    _D("Drift", "/intelligence/drift", "activity", "Model drift monitoring"),
                ],
            },
            {
                "label": "Explore",
                "items": [
                    _D(
                        "Playground",
                        "/intelligence/playground",
                        "message-square",
                        "Chat over your data",
                    ),
                    _D("Traces", "/intelligence/traces", "git-branch", "Agent execution traces"),
                    _D("Features", "/intelligence/features", "layers", "Feature store and groups"),
                    _D(
                        "Predictions",
                        "/intelligence/predictions",
                        "zap",
                        "Run inference against models",
                    ),
                    _D(
                        "Embeddings",
                        "/intelligence/embeddings",
                        "database",
                        "Semantic search collections",
                    ),
                ],
            },
            {
                "label": "Build",
                "items": [
                    _D(
                        "Experiments",
                        "/intelligence/experiments",
                        "flask-conical",
                        "Track and compare ML runs",
                    ),
                    _D("Agents", "/intelligence/agents", "bot", "Configure autonomous agents"),
                    _D("Tools", "/intelligence/tools", "wrench", "Tool catalog — 3-tier registry"),
                    _D(
                        "Fine-tune",
                        "/intelligence/finetune",
                        "cpu",
                        "Train models on lakehouse data",
                    ),
                ],
            },
        ],
    },
    {
        "id": "secops",
        "label": "SecOps",
        "icon": "shield",
        "color": "#f87171",
        "href": "/secops",
        "prefix": "/secops",
        "page_groups": [
            {
                "label": "Monitor",
                "items": [
                    _D("Overview", "/secops", "eye", "Privacy and security overview"),
                    _D("Audit log", "/secops/audit", "scroll", "Action audit trail"),
                ],
            },
            {
                "label": "Explore",
                "items": [
                    _D("Privacy", "/secops/privacy", "lock", "PII detection and masking"),
                    _D("Policies", "/secops/policies", "file-check", "Data access policies"),
                ],
            },
        ],
    },
    {
        "id": "system",
        "label": "System",
        "icon": "settings-2",
        "color": "#22c55e",
        "href": "/system/status",
        "prefix": "/system/",
        "page_groups": [
            {
                "label": "Monitor",
                "items": [
                    _D("Health", "/system/status", "heart-pulse", "Component health checks"),
                    _D("Alerting", "/system/alerting", "bell", "Alert rules and channels"),
                ],
            },
            {
                "label": "Build",
                "items": [
                    _D(
                        "Scheduler", "/system/scheduler", "clock", "Cron schedules and DAG triggers"
                    ),
                    _D("Compaction", "/system/compaction", "minimize-2", "Table compaction jobs"),
                    _D("Settings", "/system/settings", "sliders", "dex.yaml configuration"),
                ],
            },
        ],
    },
]


def _active_domain_id(current_path: str) -> str:
    """Return the domain id that owns *current_path*, or 'hub' for root."""
    if not current_path or current_path == "/":
        return "hub"
    for dom in NAV_DOMAINS:
        if current_path.startswith(str(dom["prefix"])):
            return str(dom["id"])
    return "hub"


def _build_page_groups(
    domain_id: str,
    current_path: str,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Return (domain_label, domain_color, page_groups) for *domain_id*."""
    for dom in NAV_DOMAINS:
        if dom["id"] != domain_id:
            continue
        groups: list[dict[str, Any]] = []
        for grp in dom.get("page_groups", []):
            items_active: list[dict[str, Any]] = []
            for it in grp["items"]:
                is_active = current_path == it["href"] or (
                    it["href"] != "/" and current_path.startswith(it["href"])
                )
                items_active.append({**it, "active": is_active})
            groups.append({**grp, "items": items_active})
        return dom["label"], dom["color"], groups
    return "DEX Studio", "#60a5fa", []


def build_two_rail(
    current_path: str,
) -> tuple[list[dict[str, Any]], str, str, list[dict[str, Any]]]:
    """Return (rail_items, domain_label, domain_color, page_groups) for current_path.

    rail_items: list of dicts with id/label/icon/color/href/active fields.
    domain_label/color: active domain display info for the page panel header.
    page_groups: Monitor/Explore/Build groups for the active domain.
    """
    active_id = _active_domain_id(current_path)

    rail_items: list[dict[str, Any]] = [
        {
            "id": dom["id"],
            "label": dom["label"],
            "icon": dom["icon"],
            "color": dom["color"],
            "href": dom["href"],
            "active": dom["id"] == active_id,
        }
        for dom in NAV_DOMAINS
    ]

    if active_id == "hub":
        return rail_items, "DEX Studio", "#60a5fa", []

    domain_label, domain_color, page_groups = _build_page_groups(active_id, current_path)
    return rail_items, domain_label, domain_color, page_groups
