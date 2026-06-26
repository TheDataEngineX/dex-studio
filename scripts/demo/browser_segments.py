"""Static screenshot capture for DEX Studio docs.

Starts the app on port 7861 (one above prod) so it never collides with a
running dev server, seeds MovieDEX data, then visits every major page and
saves a high-DPI screenshot to docs/screenshots/.

Usage:
    uv run poe screenshots          # via pyproject.toml task
    uv run python scripts/demo/browser_segments.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO = SCRIPTS.parent
SEED_SCRIPT = SCRIPTS / "seed_moviedex.py"
SCREENSHOTS_DIR = REPO / "docs" / "screenshots"
PORT = 7861
DEX_CONFIG = REPO / "examples" / "movie-dex" / "dex.yaml"

# ---------------------------------------------------------------------------
# Pages to capture.  Each entry is (slug, path).
# The slug becomes the output filename: {slug}.png
# ---------------------------------------------------------------------------
PAGES: list[tuple[str, str]] = [
    # Hub
    ("home", "/"),
    # Data — Explore
    ("data-sources", "/data/sources"),
    ("data-catalog", "/data/catalog"),
    ("data-warehouse", "/data/warehouse"),
    ("data-sql", "/data/sql"),
    ("data-lineage", "/data/lineage"),
    ("data-quality", "/data/quality"),
    ("data-schema", "/data/schema"),
    # Pipelines
    ("data-pipelines", "/data/pipelines"),
    ("data-transforms", "/data/transforms"),
    ("data-streaming", "/data/streaming"),
    ("data-watermarks", "/data/watermarks"),
    ("data-backfill", "/data/backfill"),
    ("data-dashboard", "/data/dashboard"),
    # Intelligence
    ("intelligence-playground", "/intelligence/playground"),
    ("intelligence-dashboard", "/intelligence/dashboard"),
    ("intelligence-models", "/intelligence/models"),
    ("intelligence-experiments", "/intelligence/experiments"),
    ("intelligence-features", "/intelligence/features"),
    ("intelligence-predictions", "/intelligence/predictions"),
    ("intelligence-drift", "/intelligence/drift"),
    ("intelligence-agents", "/intelligence/agents"),
    ("intelligence-tools", "/intelligence/tools"),
    ("intelligence-traces", "/intelligence/traces"),
    ("intelligence-embeddings", "/intelligence/embeddings"),
    ("intelligence-finetune", "/intelligence/finetune"),
    # SecOps
    ("secops-overview", "/secops"),
    ("secops-privacy", "/secops/privacy"),
    ("secops-audit", "/secops/audit"),
    ("secops-policies", "/secops/policies"),
    # System
    ("system-status", "/system/status"),
    ("system-alerting", "/system/alerting"),
    ("system-compaction", "/system/compaction"),
    ("system-settings", "/system/settings"),
    ("system-logs", "/system/logs"),
    ("system-costs", "/system/costs"),
    ("system-components", "/system/components"),
    ("system-runs", "/system/runs"),
]


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
                print("  server ready.")
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
# Screenshot helpers
# ---------------------------------------------------------------------------


def _login(page: object, base: str) -> None:  # type: ignore[type-arg]
    """Authenticate the Playwright page session with the demo passphrase."""
    page.goto(f"{base}/login", wait_until="load", timeout=60000)  # type: ignore[attr-defined]
    page.fill("input[name='passphrase']", "demo-key")  # type: ignore[attr-defined]
    page.locator("button[type='submit']").click()  # type: ignore[attr-defined]
    page.wait_for_load_state("load", timeout=60000)  # type: ignore[attr-defined]
    page.wait_for_timeout(600)  # type: ignore[attr-defined]


def _screenshot(page: object, dest: Path) -> None:  # type: ignore[type-arg]
    """Wait for the page to settle, then take a full-page screenshot."""
    # Allow HTMX / deferred loads to complete.
    page.wait_for_timeout(800)  # type: ignore[attr-defined]
    page.screenshot(path=str(dest), full_page=True)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    skip_seed = "--no-seed" in sys.argv
    if not skip_seed:
        _seed_moviedex()

    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

    server = _start_server()
    base = f"http://127.0.0.1:{PORT}"

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                device_scale_factor=2,
            )
            page = ctx.new_page()

            # Authenticate once — session cookie persists for this context.
            _login(page, base)

            for slug, path in PAGES:
                dest = SCREENSHOTS_DIR / f"{slug}.png"
                print(f"  screenshot: {path} → {dest.name}")
                page.goto(f"{base}{path}", wait_until="load", timeout=60000)
                _screenshot(page, dest)

            ctx.close()
            browser.close()

    finally:
        _stop_server(server)

    print(f"--- Done. {len(PAGES)} screenshots saved to {SCREENSHOTS_DIR}")


if __name__ == "__main__":
    main()
