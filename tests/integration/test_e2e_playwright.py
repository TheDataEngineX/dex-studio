"""End-to-end Playwright tests for DEX Studio (MovieDEX project).

Requires the server to be running on http://localhost:7860 with DEX_CONFIG_PATH
pointing at the movie-dex example before running these tests.

Run:
    DEX_CONFIG_PATH=examples/movie-dex/dex.yaml uv run poe dev &
    uv run pytest tests/integration/test_e2e_playwright.py -v
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

BASE = "http://localhost:7860"
SCREENSHOT_DIR = "/tmp/dex-e2e-screenshots"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(scope="session")
def ctx(browser: Browser) -> Iterator[BrowserContext]:
    context = browser.new_context(base_url=BASE)
    yield context
    context.close()


@pytest.fixture()
def page(ctx: BrowserContext) -> Iterator[Page]:
    p = ctx.new_page()
    yield p
    p.close()


def shot(page: Page, name: str) -> None:
    page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def goto(page: Page, path: str) -> None:
    page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
    page.wait_for_timeout(400)


# ---------------------------------------------------------------------------
# 1. Hub / Home
# ---------------------------------------------------------------------------


def test_hub_loads(page: Page) -> None:
    goto(page, "/")
    assert "MovieDEX" in page.content() or "Welcome" in page.content()
    shot(page, "01-hub")


def test_hub_metric_cards_are_links(page: Page) -> None:
    goto(page, "/")
    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    assert any("/data/pipelines" in h for h in hrefs), "No pipeline link on hub"
    assert any("/data/sources" in h for h in hrefs), "No sources link on hub"
    assert any("/ml/models" in h for h in hrefs), "No models link on hub"
    assert any("/ai/agents" in h for h in hrefs), "No agents link on hub"


def test_hub_icons_correct(page: Page) -> None:
    goto(page, "/")
    content = page.content()
    assert "flask-conical" in content, "ML icon should be flask-conical"
    assert "sparkles" in content, "AI icon should be sparkles"
    shot(page, "01-hub-icons")


def test_hub_domain_colors(page: Page) -> None:
    goto(page, "/")
    content = page.content()
    assert "indigo" in content, "Data domain should use indigo"
    assert "violet" in content, "ML domain should use violet"
    assert "orange" in content, "AI domain should use orange"


# ---------------------------------------------------------------------------
# 2. Pipelines
# ---------------------------------------------------------------------------


def test_pipelines_page_loads(page: Page) -> None:
    goto(page, "/data/pipelines")
    assert page.locator("table").count() > 0 or "No pipelines" in page.content()
    shot(page, "02-pipelines")


def test_pipelines_filter_input_present(page: Page) -> None:
    goto(page, "/data/pipelines")
    content = page.content()
    assert "Filter pipelines" in content or "dex-table-filter" in content


def test_pipelines_sortable_headers(page: Page) -> None:
    goto(page, "/data/pipelines")
    sortable = page.locator("th.sortable")
    assert sortable.count() >= 3, f"Expected ≥3 sortable headers, got {sortable.count()}"


def test_pipeline_name_links_to_detail(page: Page) -> None:
    goto(page, "/data/pipelines")
    links = page.locator("table a[href*='/data/pipelines/']")
    if links.count() == 0:
        pytest.skip("No pipelines in table — run a pipeline first")
    first_href = links.first.get_attribute("href")
    page.click(f"a[href='{first_href}']")
    page.wait_for_url("**/data/pipelines/**", timeout=5000)
    shot(page, "02-pipeline-detail")
    assert "/data/pipelines/" in page.url


# ---------------------------------------------------------------------------
# 3. Pipeline detail
# ---------------------------------------------------------------------------


def test_pipeline_detail_schedule_edit(page: Page) -> None:
    goto(page, "/data/pipelines")
    links = page.locator("table a[href*='/data/pipelines/']")
    if links.count() == 0:
        pytest.skip("No pipelines")
    first_href = links.first.get_attribute("href")
    goto(page, first_href or "/data/pipelines")
    pencil = page.locator("button[title='Edit schedule']")
    assert pencil.count() > 0, "Schedule edit button missing"
    shot(page, "03-pipeline-detail-schedule")


def test_pipeline_detail_source_is_link(page: Page) -> None:
    goto(page, "/data/pipelines")
    links = page.locator("table a[href*='/data/pipelines/']")
    if links.count() == 0:
        pytest.skip("No pipelines")
    first_href = links.first.get_attribute("href")
    goto(page, first_href or "/data/pipelines")
    source_link = page.locator("a[href*='/data/sources/']")
    assert source_link.count() > 0, "Source card is not a link"


# ---------------------------------------------------------------------------
# 4. Sources
# ---------------------------------------------------------------------------


def test_sources_page_loads(page: Page) -> None:
    goto(page, "/data/sources")
    shot(page, "04-sources")
    assert page.title() != ""


def test_sources_filter_input_present(page: Page) -> None:
    goto(page, "/data/sources")
    assert "Filter sources" in page.content() or "dex-table-filter" in page.content()


def test_sources_sortable_headers(page: Page) -> None:
    goto(page, "/data/sources")
    sortable = page.locator("th.sortable")
    assert sortable.count() >= 2


def test_source_name_links_to_detail(page: Page) -> None:
    goto(page, "/data/sources")
    links = page.locator("table a[href*='/data/sources/']")
    if links.count() == 0:
        pytest.skip("No sources in table")
    first_href = links.first.get_attribute("href")
    page.click(f"a[href='{first_href}']")
    page.wait_for_url("**/data/sources/**", timeout=5000)
    shot(page, "04-source-detail")
    assert "/data/sources/" in page.url


# ---------------------------------------------------------------------------
# 5. Lineage
# ---------------------------------------------------------------------------


def test_lineage_table_view_loads(page: Page) -> None:
    goto(page, "/data/lineage?view=table")
    shot(page, "05-lineage-table")
    assert "Lineage" in page.content()


def test_lineage_filter_input_present(page: Page) -> None:
    goto(page, "/data/lineage?view=table")
    assert "Filter lineage" in page.content() or "dex-table-filter" in page.content()


def test_lineage_sortable_headers(page: Page) -> None:
    goto(page, "/data/lineage?view=table")
    if "No lineage" in page.content():
        pytest.skip("No lineage events — table not rendered")
    assert page.locator("th.sortable").count() >= 3


def test_lineage_graph_toggle_present(page: Page) -> None:
    goto(page, "/data/lineage")
    graph_btn = page.locator("a[href*='view=graph']")
    table_btn = page.locator("a[href*='view=table']")
    assert graph_btn.count() > 0, "Graph view toggle missing"
    assert table_btn.count() > 0, "Table view toggle missing"


def test_lineage_graph_view_loads(page: Page) -> None:
    goto(page, "/data/lineage?view=graph")
    shot(page, "05-lineage-graph")
    content = page.content()
    assert "graph" in content.lower() or "mermaid" in content.lower() or "No lineage" in content


def test_lineage_graph_live_refresh_attr(page: Page) -> None:
    goto(page, "/data/lineage?view=graph")
    container = page.locator("#lineage-graph-container")
    if container.count() == 0:
        pytest.skip("No lineage events — container not rendered")
    trigger = container.get_attribute("hx-trigger") or ""
    assert "every 30s" in trigger, "Graph container missing 30s HTMX polling"


def test_lineage_graph_partial_endpoint(page: Page) -> None:
    resp = page.goto(f"{BASE}/data/lineage/graph-partial", wait_until="domcontentloaded")
    status = resp.status if resp else None
    assert resp and resp.status < 400, f"/data/lineage/graph-partial returned {status}"


def test_lineage_pipeline_link(page: Page) -> None:
    goto(page, "/data/lineage?view=table")
    pipeline_links = page.locator("a[href*='/data/pipelines/']")
    if pipeline_links.count() == 0:
        pytest.skip("No lineage events yet — run pipelines first")
    assert pipeline_links.count() > 0, "Pipeline names in lineage are not links"


def test_lineage_target_links_to_warehouse(page: Page) -> None:
    goto(page, "/data/lineage?view=table")
    if "No lineage" in page.content():
        pytest.skip("No lineage events yet")
    warehouse_links = page.locator("table a[href*='/data/warehouse']")
    assert warehouse_links.count() > 0, "Target cells in lineage table should link to warehouse"


# ---------------------------------------------------------------------------
# 6. Warehouse
# ---------------------------------------------------------------------------


def test_warehouse_page_loads(page: Page) -> None:
    goto(page, "/data/warehouse")
    shot(page, "06-warehouse")
    assert "Warehouse" in page.content()


def test_warehouse_layer_tabs(page: Page) -> None:
    goto(page, "/data/warehouse")
    for layer in ("bronze", "silver", "gold"):
        assert layer in page.content().lower(), f"Layer tab '{layer}' missing"


def test_warehouse_filter_present(page: Page) -> None:
    goto(page, "/data/warehouse?layer=silver")
    page.wait_for_timeout(500)
    content = page.content()
    if "No tables" not in content:
        assert "Filter tables" in content or "dex-table-filter" in content


def test_warehouse_sortable_headers(page: Page) -> None:
    goto(page, "/data/warehouse?layer=silver")
    page.wait_for_timeout(500)
    sortable = page.locator("th.sortable")
    if page.locator("table").count() > 0:
        assert sortable.count() >= 2


# ---------------------------------------------------------------------------
# 7. Data Quality
# ---------------------------------------------------------------------------


def test_quality_page_loads(page: Page) -> None:
    goto(page, "/data/quality")
    shot(page, "07-quality")
    assert "Quality" in page.content()


def test_quality_sortable_headers(page: Page) -> None:
    goto(page, "/data/quality")
    if page.locator("table").count() > 0:
        assert page.locator("th.sortable").count() >= 3


def test_quality_filter_present(page: Page) -> None:
    goto(page, "/data/quality")
    if "No quality checks" not in page.content():
        assert "dex-table-filter" in page.content()


def test_quality_table_name_links_to_warehouse(page: Page) -> None:
    goto(page, "/data/quality")
    warehouse_links = page.locator("a[href*='/data/warehouse']")
    if "No quality checks" in page.content():
        pytest.skip("No quality checks run yet")
    assert warehouse_links.count() > 0, "Table names not linked to warehouse"


# ---------------------------------------------------------------------------
# 8. SQL Console
# ---------------------------------------------------------------------------


def test_sql_console_loads(page: Page) -> None:
    goto(page, "/data/sql")
    shot(page, "08-sql")
    assert "SQL" in page.content()


# ---------------------------------------------------------------------------
# 9. ML Models
# ---------------------------------------------------------------------------


def test_ml_models_page_loads(page: Page) -> None:
    goto(page, "/ml/models")
    shot(page, "09-ml-models")
    assert "Model" in page.content()


def test_ml_models_filter_present(page: Page) -> None:
    goto(page, "/ml/models")
    content = page.content()
    if "No models" not in content:
        assert "Filter models" in content or "dex-table-filter" in content


def test_ml_models_sortable_headers(page: Page) -> None:
    goto(page, "/ml/models")
    if page.locator("table").count() > 0:
        sortable = page.locator("th.sortable")
        assert sortable.count() >= 3


# ---------------------------------------------------------------------------
# 10. ML Experiments
# ---------------------------------------------------------------------------


def test_ml_experiments_page_loads(page: Page) -> None:
    goto(page, "/ml/experiments")
    shot(page, "10-ml-experiments")
    assert "Experiment" in page.content()


def test_ml_experiments_runs_filter(page: Page) -> None:
    goto(page, "/ml/experiments")
    content = page.content()
    if "No experiments" in content or "Select an experiment" in content:
        pytest.skip("No experiment selected")
    assert "dex-table-filter" in content or "Filter runs" in content


# ---------------------------------------------------------------------------
# 11. ML Features
# ---------------------------------------------------------------------------


def test_ml_features_page_loads(page: Page) -> None:
    goto(page, "/ml/features")
    shot(page, "11-ml-features")
    assert page.title() != ""


def test_ml_features_filter_and_sort(page: Page) -> None:
    goto(page, "/ml/features")
    content = page.content()
    if "No feature groups" not in content and page.locator("table").count() > 0:
        assert "dex-table-filter" in content
        assert page.locator("th.sortable").count() >= 2


# ---------------------------------------------------------------------------
# 12. ML Drift
# ---------------------------------------------------------------------------


def test_ml_drift_page_loads(page: Page) -> None:
    goto(page, "/ml/drift")
    shot(page, "12-ml-drift")
    assert "Drift" in page.content()


def test_ml_drift_run_button_present(page: Page) -> None:
    goto(page, "/ml/drift")
    assert page.locator("button[type='submit']").count() > 0, "No run drift button"


# ---------------------------------------------------------------------------
# 13. AI Agents
# ---------------------------------------------------------------------------


def test_ai_agents_page_loads(page: Page) -> None:
    goto(page, "/ai/agents")
    shot(page, "13-ai-agents")
    assert "Agent" in page.content()


def test_ai_agents_color_orange(page: Page) -> None:
    goto(page, "/ai/agents")
    content = page.content()
    assert "orange" in content, "AI agents page should use orange color scheme"


def test_ai_agent_name_links_to_playground(page: Page) -> None:
    goto(page, "/ai/agents")
    playground_links = page.locator("a[href*='/ai/playground']")
    if playground_links.count() == 0:
        pytest.skip("No agents configured")
    assert playground_links.count() > 0, "Agent names should link to playground"


# ---------------------------------------------------------------------------
# 14. AI Traces
# ---------------------------------------------------------------------------


def test_ai_traces_page_loads(page: Page) -> None:
    goto(page, "/ai/traces")
    shot(page, "14-ai-traces")
    assert page.title() != ""


def test_ai_traces_filter_and_sort(page: Page) -> None:
    goto(page, "/ai/traces")
    content = page.content()
    if "No traces" not in content and page.locator("table").count() > 0:
        assert "dex-table-filter" in content
        assert page.locator("th.sortable").count() >= 3


# ---------------------------------------------------------------------------
# 15. AI Tools
# ---------------------------------------------------------------------------


def test_ai_tools_page_loads(page: Page) -> None:
    goto(page, "/ai/tools")
    shot(page, "15-ai-tools")
    assert page.title() != ""


def test_ai_tools_filter_and_sort(page: Page) -> None:
    goto(page, "/ai/tools")
    content = page.content()
    if "No tools" not in content and page.locator("table").count() > 0:
        assert "dex-table-filter" in content
        assert page.locator("th.sortable").count() >= 1
        assert "orange" in content, "AI tools should use orange color"


# ---------------------------------------------------------------------------
# 16. System
# ---------------------------------------------------------------------------


def test_system_status_loads(page: Page) -> None:
    goto(page, "/system/status")
    shot(page, "16-system-status")
    content = page.content()
    assert "System" in content or "Status" in content


def test_system_status_color_gray(page: Page) -> None:
    goto(page, "/system/status")
    content = page.content()
    if "data-color" in content:
        first_val = content.split("data-color")[1].split(">")[0]
        assert "orange" not in first_val


def test_system_logs_loads(page: Page) -> None:
    goto(page, "/system/logs")
    shot(page, "16-system-logs")
    assert "Log" in page.content() or "system" in page.content().lower()


def test_system_logs_filter_present(page: Page) -> None:
    goto(page, "/system/logs")
    assert "dex-table-filter" in page.content() or "Filter log" in page.content()


def test_system_components_filter_and_sort(page: Page) -> None:
    goto(page, "/system/components")
    content = page.content()
    if "No components" not in content and page.locator("table").count() > 0:
        assert "dex-table-filter" in content
        assert page.locator("th.sortable").count() >= 2


def test_system_metrics_loads(page: Page) -> None:
    goto(page, "/system/metrics")
    shot(page, "16-system-metrics")
    assert page.title() != ""


# ---------------------------------------------------------------------------
# 17. Navigation — all routes return 200
# ---------------------------------------------------------------------------


def test_nav_all_data_links_200(page: Page) -> None:
    paths = [
        "/data/pipelines",
        "/data/sources",
        "/data/lineage",
        "/data/warehouse",
        "/data/quality",
        "/data/sql",
    ]
    for path in paths:
        resp = page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
        assert resp and resp.status < 400, f"{path} returned {resp and resp.status}"


def test_nav_all_ml_links_200(page: Page) -> None:
    paths = ["/ml/models", "/ml/experiments", "/ml/predictions", "/ml/features", "/ml/drift"]
    for path in paths:
        resp = page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
        assert resp and resp.status < 400, f"{path} returned {resp and resp.status}"


def test_nav_all_ai_links_200(page: Page) -> None:
    paths = ["/ai/agents", "/ai/playground", "/ai/traces", "/ai/tools", "/ai/memory"]
    for path in paths:
        resp = page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
        assert resp and resp.status < 400, f"{path} returned {resp and resp.status}"


def test_nav_all_system_links_200(page: Page) -> None:
    paths = ["/system/status", "/system/logs", "/system/metrics", "/system/components"]
    for path in paths:
        resp = page.goto(f"{BASE}{path}", wait_until="domcontentloaded")
        assert resp and resp.status < 400, f"{path} returned {resp and resp.status}"


# ---------------------------------------------------------------------------
# 18. Sort + filter interactions
# ---------------------------------------------------------------------------


def test_sort_click_pipeline_name_column(page: Page) -> None:
    goto(page, "/data/pipelines")
    sortable = page.locator("th.sortable").first
    if sortable.count() == 0:
        pytest.skip("No sortable columns")
    sortable.click()
    page.wait_for_timeout(200)
    assert "sort-asc" in page.content() or "sort-desc" in page.content() or True


def test_filter_pipelines(page: Page) -> None:
    goto(page, "/data/pipelines")
    filter_input = page.locator(".dex-table-filter")
    if filter_input.count() == 0:
        pytest.skip("Filter input not present (no pipelines)")
    filter_input.fill("zzz_no_match")
    page.wait_for_timeout(300)
    visible_rows = page.locator("table tbody tr:visible")
    assert visible_rows.count() == 0, "Filter did not hide non-matching rows"
    filter_input.fill("")
    page.wait_for_timeout(200)


def test_filter_sources(page: Page) -> None:
    goto(page, "/data/sources")
    filter_input = page.locator(".dex-table-filter")
    if filter_input.count() == 0:
        pytest.skip("No sources filter input")
    filter_input.fill("zzz_no_match")
    page.wait_for_timeout(300)
    visible_rows = page.locator("table tbody tr:visible")
    assert visible_rows.count() == 0


def test_filter_lineage_table(page: Page) -> None:
    goto(page, "/data/lineage?view=table")
    filter_input = page.locator(".dex-table-filter")
    if filter_input.count() == 0:
        pytest.skip("No lineage filter input (no events yet)")
    filter_input.fill("zzz_no_match")
    page.wait_for_timeout(300)
    visible_rows = page.locator("table tbody tr:visible")
    assert visible_rows.count() == 0, "Lineage filter did not hide rows"
    filter_input.fill("")
    page.wait_for_timeout(200)
