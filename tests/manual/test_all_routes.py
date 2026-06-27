"""Comprehensive manual smoke test — visits every route on a running server."""

import argparse

import httpx

BASE = "http://127.0.0.1:7860"
VERBOSE = False


def ok(resp: httpx.Response, path: str) -> None:
    status = resp.status_code
    ok_redirect = status in (200, 302, 303, 307, 308)
    flag = "✓" if ok_redirect else "✗"
    extra = ""
    if status in (302, 303, 307, 308):
        extra = f" → {resp.headers.get('location', '?')}"
    if not ok_redirect or VERBOSE:
        print(f"  {flag} {status} {path}{extra}")
    if not ok_redirect:
        print(f"     Body: {(resp.text[:200])}")


def main() -> None:  # noqa: C901
    global VERBOSE
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    VERBOSE = args.verbose
    base = args.base

    client = httpx.Client(base_url=base, follow_redirects=False, timeout=30)

    # ── 1. Auth setup: set a password and log in ──────────────────────────
    print("\n=== AUTH SETUP ===")
    # Check if password already exists
    resp = client.get("/login")
    ok(resp, "GET /login")

    need_setup = resp.status_code != 200 or "/setup" in str(resp.url) or resp.status_code in (302, 303)  # noqa: E501
    if need_setup:
        # Clean up: reset password first
        client.cookies.clear()
        # POST directly to /setup — setup route doesn't need CSRF
        resp = client.post("/setup", data={"password": "testpass123"})
        ok(resp, "POST /setup (create password)")
        if resp.status_code == 303:
            resp = client.get(resp.headers["location"])
            ok(resp, "→ /login")
    else:
        # Password already exists from prior run
        print("  password already exists")

    # Now log in
    resp = client.get("/login")
    ok(resp, "GET /login")
    if resp.status_code == 200:
        csrf = extract_csrf(resp.text) or extract_json_csrf(resp.text)
        resp = client.post("/login", data={"passphrase": "testpass123", "_csrf": csrf or ""})
        ok(resp, "POST /login")
        if resp.status_code == 303:
            resp = client.get(resp.headers["location"])
            ok(resp, "→ / (post-login)")

    # ── 2. Health check ───────────────────────────────────────────────────
    print("\n=== HEALTH ===")
    resp = client.get("/health")
    ok(resp, "/health")

    # ── 3. Root routes ───────────────────────────────────────────────────
    print("\n=== ROOT ===")
    for path in ["/", "/privacy/", "/onboarding"]:
        resp = client.get(path)
        ok(resp, path)

    # ── 4. System routes ─────────────────────────────────────────────────
    print("\n=== SYSTEM ===")
    for path in ["/system", "/system/metrics-live", "/system/metrics",
                 "/system/logs", "/system/components", "/system/runs",
                 "/system/costs", "/system/compaction", "/system/alerting",
                 "/system/traces", "/system/activity", "/system/incidents",
                 "/system/settings", "/system/connection",
                 "/system/logs/stream", "/system/status"]:
        resp = client.get(path)
        ok(resp, path)

    # ── 5. Data routes ───────────────────────────────────────────────────
    print("\n=== DATA ===")
    data_paths = [
        "/data", "/data/dashboard",
        "/data/pipelines", "/data/pipelines/status", "/data/pipelines/runs",
        "/data/pipelines/runs/all", "/data/sources", "/data/transforms",
        "/data/lakehouse", "/data/lakehouse/tables",
        "/data/warehouse", "/data/warehouse/tables",
        "/data/lineage", "/data/quality", "/data/catalog",
        "/data/streaming", "/data/watermarks",
        "/data/schema", "/data/backfill",
        "/data/asset-graph", "/data/contracts", "/data/templates",
        "/data/sql",
    ]
    for path in data_paths:
        resp = client.get(path)
        ok(resp, path)

    # ── 6. Intelligence routes ───────────────────────────────────────────
    print("\n=== INTELLIGENCE ===")
    intel_paths = [
        "/intelligence", "/intelligence/dashboard",
        "/intelligence/models", "/intelligence/experiments",
        "/intelligence/predictions", "/intelligence/features",
        "/intelligence/drift", "/intelligence/playground",
        "/intelligence/agents", "/intelligence/tools",
        "/intelligence/traces", "/intelligence/embeddings",
        "/intelligence/finetune", "/intelligence/stream",
        "/intelligence/context",
        "/intelligence/hyperopt", "/intelligence/ab-test",
        "/intelligence/rag-eval", "/intelligence/hitl",
        "/intelligence/predict/models",
    ]
    for path in intel_paths:
        resp = client.get(path)
        ok(resp, path)

    # ── 7. API routes ────────────────────────────────────────────────────
    print("\n=== API ===")
    api_paths = [
        "/api/scheduler/status", "/api/pipelines",
        "/api/watermarks", "/api/compaction/status",
        "/api/schema/{pipeline}/drift",
        "/api/alerts", "/api/quality/contracts",
    ]
    for path in api_paths:
        resp = client.get(path)
        ok(resp, path)

    # ── 8. SecOps routes ────────────────────────────────────────────────
    print("\n=== SECOPS ===")
    secops_paths = [
        "/secops", "/secops/privacy", "/secops/policies",
        "/secops/audit", "/secops/alerts",
    ]
    for path in secops_paths:
        resp = client.get(path)
        ok(resp, path)

    # ── 9. Detailed routes (pipeline/source details) ─────────────────────
    print("\n=== DETAILED (data-driven) ===")
    resp = client.get("/api/pipelines")
    if resp.status_code == 200:
        try:
            pipelines = resp.json().get("pipelines", resp.json().get("data", []))
            if isinstance(pipelines, list) and pipelines:
                for p in pipelines[:3]:
                    name = p if isinstance(p, str) else p.get("name", "")
                    if name:
                        resp = client.get(f"/data/pipelines/{name}")
                        ok(resp, f"/data/pipelines/{name}")
                        resp = client.get(f"/data/pipelines/{name}/runs")
                        ok(resp, f"/data/pipelines/{name}/runs")
        except Exception:
            pass

    resp = client.get("/data/sources")
    if resp.status_code == 200:
        pass  # sources rendered inline, no separate detail pages to enumerate

    resp = client.get("/data/catalog")
    if resp.status_code == 200:
        pass

    # ── 10. Summary ──────────────────────────────────────────────────────
    print("\n=== DONE ===")


def extract_csrf(html: str) -> str:
    """Extract CSRF token from HTML meta tag or input field."""
    import re
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""


def extract_json_csrf(html: str) -> str:
    """Extract CSRF token from inline JSON."""
    import re
    m = re.search(r'"_csrf":\s*"([^"]+)"', html)
    return m.group(1) if m else ""


if __name__ == "__main__":
    main()
