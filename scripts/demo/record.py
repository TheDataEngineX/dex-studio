"""Narrative product demo for DEX Studio — produces demo.gif and demo-full.mp4.

Story arc:
  Act 0  — Login
  Act 1  — Data Foundation  (hub → sources → pipelines → catalog → SQL → quality → lineage)
  Act 2  — Pipeline Ops     (transforms → watermarks → backfill → schema → streaming)
  Act 3  — Intelligence     (dashboard → playground → models → experiments → agents →
                              traces → drift → embeddings → features → predictions → finetune)
  Act 4  — Governance & Ops (secops overview → privacy → audit → system health →
                              alerting → compaction → logs → settings → costs)

The Playwright video recorder captures the full session as a WebM, which is
then renamed to demo-full.mp4.  A GIF is generated from the WebM via ffmpeg
(if available); otherwise the step is skipped gracefully.

Usage:
    uv run python scripts/demo/record.py
    uv run python scripts/demo/record.py --seed-only   # seed data then exit
    uv run python scripts/demo/record.py --video-only  # skip seed, re-record
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO = SCRIPTS.parent
SEED_SCRIPT = SCRIPTS / "seed_moviedex.py"
DOCS_DIR = REPO / "docs"
PORT = 7862
DEX_CONFIG = REPO / "examples" / "movie-dex" / "dex.yaml"

VIDEO_PATH = DOCS_DIR / "demo-full.mp4"
GIF_PATH = DOCS_DIR / "demo.gif"


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


def _seed_moviedex() -> None:
    print("--- Seeding MovieDEX...")
    env = os.environ.copy()
    env["PYTHONPATH"] = f"src{os.pathsep}../dataenginex/src"
    result = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Seed stderr:", result.stderr[-2000:])
        print("Seed stdout:", result.stdout[-2000:])
        result.check_returncode()
    print("Seed complete.")


def _start_server() -> subprocess.Popen:
    import urllib.error
    import urllib.request

    print(f"--- Starting DEX Studio on port {PORT}...")

    # Pre-write a known password hash so the demo always uses "demo-key".
    from dex_studio.auth import _hash_password  # type: ignore[import-not-found]

    hf = Path.home() / ".dex-studio" / "auth.hash"
    hf.parent.mkdir(parents=True, exist_ok=True)
    hf.write_text(_hash_password("demo-key"))
    hf.chmod(0o600)

    env = os.environ.copy()
    env["DEX_CONFIG_PATH"] = str(DEX_CONFIG)
    env["DEX_STUDIO_SESSION_SECRET"] = "d" * 32
    env["PYTHONPATH"] = "src"
    env["UV_PROJECT_ENVIRONMENT"] = str(Path(sys.prefix))

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "dex_studio.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--loop",
            "uvloop",
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    health_url = f"http://127.0.0.1:{PORT}/health"
    for _ in range(60):
        try:
            resp = urllib.request.urlopen(health_url, timeout=2)
            if resp.getcode() == 200:
                print("  server ready (health OK)")
                return proc
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            pass
        time.sleep(2)

    proc.kill()
    raise RuntimeError(f"Server did not become ready on port {PORT} within 120s")


def _stop_server(proc: subprocess.Popen) -> None:
    print("--- Stopping server...")
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------------------
# GIF generation
# ---------------------------------------------------------------------------


def _make_gif(video: Path, gif: Path) -> None:
    """Convert *video* to an optimised GIF via ffmpeg (skipped if not available)."""
    if shutil.which("ffmpeg") is None:
        print("  [skip] ffmpeg not found — skipping GIF generation")
        return
    # Two-pass palette approach for smallest file with best colour fidelity.
    palette = gif.with_suffix(".palette.png")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(video),
                "-vf", "fps=12,scale=1280:-1:flags=lanczos,palettegen=stats_mode=diff",
                str(palette),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(video),
                "-i", str(palette),
                "-lavfi", "fps=12,scale=1280:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer",
                str(gif),
            ],
            check=True,
            capture_output=True,
        )
        palette.unlink(missing_ok=True)
        print(f"  GIF saved → {gif}")
    except subprocess.CalledProcessError as exc:
        print(f"  [warn] GIF generation failed: {exc.stderr.decode()[-500:]}")


# ---------------------------------------------------------------------------
# Playwright interaction helpers
# ---------------------------------------------------------------------------


def _log(msg: str) -> None:
    print(f"  {msg}")


def _smooth_move(page, selector: str, steps: int = 20) -> tuple[int, int] | None:
    """Move the mouse smoothly to the centre of *selector* over *steps* frames."""
    el = page.locator(selector)
    if el.count() == 0:
        return None
    box = el.first.bounding_box()
    if box is None:
        return None
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy, steps=steps)
    return (int(cx), int(cy))


def _hover(page, selector: str, label: str = "", delay_ms: int = 500) -> None:
    """Smooth-move the cursor to *selector*, wait *delay_ms*, then continue."""
    pos = _smooth_move(page, selector)
    if pos is None:
        if label:
            _log(f"    [skip hover] {label}")
        return
    page.wait_for_timeout(delay_ms)


def _goto(page, path: str, base: str, settle_ms: int = 400) -> None:
    """Navigate to *path* and wait for load + settle."""
    page.goto(f"{base}{path}", wait_until="load", timeout=60000)
    page.wait_for_timeout(settle_ms)


def _click_rail(page, tip: str) -> None:
    """Click the rail icon whose data-tip matches *tip*."""
    sel = f'a.rail-icon[data-tip="{tip}"]'
    _hover(page, sel, f"Rail: {tip}", 300)
    page.locator(sel).first.click()
    page.wait_for_timeout(500)


def _click_panel(page, href: str, base: str, label: str = "") -> None:
    """Click a panel sidebar item by href, falling back to direct navigation."""
    sel = f'a.panel-item[href="{href}"]'
    panel = page.locator(sel)
    if panel.count() == 0:
        _goto(page, href, base)
        return
    _hover(page, sel, label, 200)
    panel.first.click()
    page.wait_for_load_state("load", timeout=60000)
    page.wait_for_timeout(400)


# ---------------------------------------------------------------------------
# Demo acts
# ---------------------------------------------------------------------------


def _act0_login(page, base: str) -> None:
    """Authenticate with the demo passphrase."""
    _log("── Act 0: Login ──")
    page.goto(f"{base}/login", wait_until="load")
    page.wait_for_timeout(400)
    _hover(page, "input[name='passphrase']", "passphrase field", 400)
    page.fill("input[name='passphrase']", "demo-key")
    page.wait_for_timeout(200)
    _hover(page, "button[type='submit']", "sign-in button", 300)
    page.locator("button[type='submit']").click()
    page.wait_for_load_state("load", timeout=60000)
    page.wait_for_timeout(600)


def _act1_data_foundation(page, base: str) -> None:
    """Hub and data-exploration pages."""
    _log("── Act 1: Data Foundation ──")

    # Hub — the command centre
    _goto(page, "/", base, settle_ms=500)
    _log("Hub — scanning accent cards")
    # Sweep across each domain accent card if present
    for domain in ["Data", "Pipelines", "Intelligence", "SecOps", "System"]:
        _hover(
            page,
            f'a.accent-card:has(span.accent-card-domain:text-is("{domain}"))',
            f"accent: {domain}",
            350,
        )
    page.wait_for_timeout(400)

    # Sources
    _log("── Sources")
    _click_rail(page, "Data")
    _click_panel(page, "/data/sources", base, "Sources")
    _hover(page, "table.tbl tbody tr:first-child td:first-child", "first source", 600)
    _hover(page, "table.tbl tbody tr:nth-child(2) td:first-child", "second source", 400)

    # Catalog
    _log("── Catalog")
    _click_panel(page, "/data/catalog", base, "Catalog")
    page.wait_for_timeout(300)
    _hover(page, "table.tbl tbody tr:first-child", "first catalog entry", 500)
    _hover(page, "table.tbl tbody tr:nth-child(2)", "second entry", 300)

    # Warehouse
    _log("── Warehouse")
    _goto(page, "/data/warehouse", base)
    _hover(page, "table.tbl tbody tr:first-child", "first warehouse table", 500)

    # SQL Console
    _log("── SQL Console")
    _click_panel(page, "/data/sql", base, "SQL")
    _hover(page, "div.ace_editor, textarea.CodeMirror-code, #sql-editor", "SQL editor", 700)
    page.wait_for_timeout(400)

    # Data Quality
    _log("── Quality")
    _goto(page, "/data/quality", base)
    _hover(page, ".card:first-child, .metric-card:first-child", "quality summary", 600)
    _hover(page, "table.tbl tbody tr:first-child", "first quality row", 400)

    # Lineage
    _log("── Lineage")
    _goto(page, "/data/lineage", base)
    page.wait_for_timeout(400)
    # Try to hover SVG nodes if Mermaid rendered; fall back to the table view
    _hover(page, "svg g.node:first-child, .mermaid", "lineage graph", 700)
    _hover(page, "table.tbl tbody tr:first-child", "lineage table row", 400)


def _act2_pipeline_ops(page, base: str) -> None:
    """Pipeline, transform, watermark, backfill, schema, and streaming pages."""
    _log("── Act 2: Pipeline Ops ──")

    # Pipeline list
    _log("── Pipelines")
    _click_panel(page, "/data/pipelines", base, "Pipelines")
    _hover(page, "table.tbl tbody tr:first-child", "first pipeline row", 600)
    _hover(page, "table.tbl tbody tr:nth-child(2)", "second pipeline row", 400)

    # Pipeline detail — first pipeline
    first_name_el = page.locator("table.tbl tbody tr:first-child td:first-child a")
    if first_name_el.count() > 0:
        first_href = first_name_el.first.get_attribute("href") or ""
        if first_href:
            _goto(page, first_href, "", settle_ms=400)
            _hover(page, ".card:first-child, .stat-block", "pipeline stats", 500)
            # Return to list
            _goto(page, "/data/pipelines", base)

    # Transforms
    _log("── Transforms")
    _goto(page, "/data/transforms", base)
    _hover(page, "select, .pipeline-selector", "pipeline selector", 500)
    _hover(page, ".flow-canvas, .transform-node, .card:first-child", "flow canvas", 600)

    # Watermarks
    _log("── Watermarks")
    _goto(page, "/data/watermarks", base)
    _hover(page, "table.tbl tbody tr:first-child", "watermark entry", 500)

    # Backfill
    _log("── Backfill")
    _goto(page, "/data/backfill", base)
    _hover(page, "table.tbl tbody tr:first-child", "backfill pipeline row", 500)

    # Schema contracts
    _log("── Schema")
    _goto(page, "/data/schema", base)
    _hover(page, "table.tbl tbody tr:first-child, .card:first-child", "schema contract", 500)

    # Streaming
    _log("── Streaming")
    _goto(page, "/data/streaming", base)
    _hover(page, ".card:first-child, .empty-state", "streaming overview", 500)


def _act3_intelligence(page, base: str) -> None:
    """ML/AI intelligence pages — dashboard, playground, models, experiments, etc."""
    _log("── Act 3: Intelligence ──")

    _click_rail(page, "Intelligence")
    page.wait_for_timeout(300)

    # Dashboard
    _log("── ML Dashboard")
    _click_panel(page, "/intelligence/dashboard", base, "ML Dashboard")
    _hover(page, ".card:first-child, .metric-card:first-child", "dashboard summary", 600)

    # Playground
    _log("── Playground")
    _click_panel(page, "/intelligence/playground", base, "Playground")
    _hover(page, "#intelligence-playground, .chat-area, textarea", "playground input", 700)
    page.wait_for_timeout(400)

    # Models
    _log("── Models")
    _click_panel(page, "/intelligence/models", base, "Models")
    _hover(page, ".card:first-child, table.tbl tbody tr:first-child", "first model card", 600)

    # Experiments
    _log("── Experiments")
    _click_panel(page, "/intelligence/experiments", base, "Experiments")
    _hover(page, "table.tbl tbody tr:first-child", "first experiment run", 500)

    # Agents
    _log("── Agents")
    _click_panel(page, "/intelligence/agents", base, "Agents")
    _hover(page, ".card:first-child, table.tbl tbody tr:first-child", "first agent card", 600)

    # Traces
    _log("── Traces")
    _click_panel(page, "/intelligence/traces", base, "Traces")
    _hover(page, "table.tbl tbody tr:first-child", "first trace row", 500)

    # Drift
    _log("── Drift")
    _click_panel(page, "/intelligence/drift", base, "Drift")
    _hover(page, ".card:first-child, .empty-state", "drift overview", 500)

    # Embeddings
    _log("── Embeddings")
    _click_panel(page, "/intelligence/embeddings", base, "Embeddings")
    _hover(page, ".card:first-child, .empty-state", "embeddings overview", 500)

    # Features
    _log("── Features")
    _click_panel(page, "/intelligence/features", base, "Features")
    _hover(page, ".card:first-child, table.tbl tbody tr:first-child", "feature store", 500)

    # Predictions
    _log("── Predictions")
    _click_panel(page, "/intelligence/predictions", base, "Predictions")
    _hover(page, ".card:first-child, .empty-state", "predictions overview", 500)

    # Tools
    _log("── Tools")
    _click_panel(page, "/intelligence/tools", base, "Tools")
    _hover(page, ".card:first-child, table.tbl tbody tr:first-child", "tool registry", 500)

    # Fine-tune
    _log("── Fine-tune")
    _click_panel(page, "/intelligence/finetune", base, "Fine-tune")
    _hover(page, ".card:first-child, .empty-state", "fine-tune overview", 500)


def _act4_governance_ops(page, base: str) -> None:
    """SecOps and System pages."""
    _log("── Act 4: Governance & Ops ──")

    # SecOps
    _click_rail(page, "SecOps")
    page.wait_for_timeout(300)

    _log("── SecOps overview")
    _click_panel(page, "/secops", base, "SecOps Overview")
    _hover(page, ".card:first-child, .metric-card:first-child", "privacy overview card", 600)

    _log("── Privacy")
    _click_panel(page, "/secops/privacy", base, "Privacy")
    _hover(page, ".card:first-child", "PII scan summary", 600)

    _log("── Audit log")
    _click_panel(page, "/secops/audit", base, "Audit")
    _hover(page, "table.tbl tbody tr:first-child", "audit entry", 500)

    _log("── Policies")
    _click_panel(page, "/secops/policies", base, "Policies")
    _hover(page, ".card:first-child, .empty-state", "policies overview", 500)

    # System
    _click_rail(page, "System")
    page.wait_for_timeout(300)

    _log("── System status")
    _click_panel(page, "/system/status", base, "Status")
    _hover(page, "#sys-metrics-foot, .metric-card:first-child", "system metrics", 600)

    _log("── Alerting")
    _click_panel(page, "/system/alerting", base, "Alerting")
    _hover(page, ".card:first-child, .empty-state", "alerting overview", 500)

    _log("── Compaction")
    _click_panel(page, "/system/compaction", base, "Compaction")
    _hover(page, ".card:first-child, .empty-state", "compaction overview", 500)

    _log("── Settings")
    _click_panel(page, "/system/settings", base, "Settings")
    _hover(page, "pre, textarea, .card:first-child", "settings YAML", 600)

    _log("── Logs")
    _goto(page, "/system/logs", base, settle_ms=700)
    _hover(page, ".log-line:first-child, .card:first-child, .empty-state", "log entries", 600)

    _log("── Costs")
    _goto(page, "/system/costs", base)
    _hover(page, ".card:first-child, .metric-card:first-child, .empty-state", "cost overview", 500)

    _log("── Components")
    _goto(page, "/system/components", base, settle_ms=500)
    _hover(page, ".card:first-child, .component-card, .empty-state", "component card", 600)

    _log("── Runs")
    _goto(page, "/system/runs", base)
    _hover(page, "table.tbl tbody tr:first-child", "run history entry", 500)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    seed_only = "--seed-only" in sys.argv
    video_only = "--video-only" in sys.argv

    if not video_only:
        _seed_moviedex()

    if seed_only:
        return

    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    server = _start_server()
    base = f"http://127.0.0.1:{PORT}"

    # Playwright writes the raw recording into the same directory as the
    # target video file.  We rename it afterwards.
    video_dir = str(DOCS_DIR)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                device_scale_factor=2,
                record_video_dir=video_dir,
                record_video_size={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            page.mouse.move(0, 0)

            _act0_login(page, base)
            _act1_data_foundation(page, base)
            _act2_pipeline_ops(page, base)
            _act3_intelligence(page, base)
            _act4_governance_ops(page, base)

            # Playwright finalises the video file on context close.
            ctx.close()
            browser.close()

        # Find the newest WebM in the docs dir and move it to the final path.
        webm_files = sorted(
            Path(video_dir).glob("*.webm"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if webm_files:
            shutil.move(str(webm_files[0]), str(VIDEO_PATH))
            print(f"  video saved → {VIDEO_PATH}")
            _make_gif(VIDEO_PATH, GIF_PATH)
        else:
            print("  [warn] no WebM recording found")

        print("--- Recording complete.")

    finally:
        _stop_server(server)


if __name__ == "__main__":
    main()
