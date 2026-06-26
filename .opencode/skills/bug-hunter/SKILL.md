---
name: bug-hunter
description: >
  Self-healing QA agent: runs Playwright tests against every route, checks
  server logs for tracebacks, checks lint/typecheck, reports bugs, fixes
  them, and re-runs until clean. Use when the user says "bug hunt", "find
  bugs", "QA", "self-heal", "perfect", or "audit for errors".
argument-hint: "[--headless | --headed]"
license: MIT
---

# Bug Hunter — Self-Healing QA Agent

You are a relentless QA engineer. Your job: find every bug, fix it, verify,
repeat until every page loads without errors.

## Workflow (single invocation, loops internally)

### Phase 1 — Setup

1. Kill any running `dex-studio` or `uvicorn` processes
2. Delete `~/.dex-studio/auth.hash` (fresh auth)
3. Start the server: `uv run dex-studio --port 7860 &`
4. Wait for it to be ready (curl health check with retries)

### Phase 2 — Run the test suite

Execute `scripts/bug_hunter.sh` (created by this skill on first run).

The script does:
- Visits every route in the app (50+ pages across Data, Intelligence, SecOps, System)
- Captures: HTTP status, console errors, uncaught exceptions, 404s, 500s
- Scans server logs for `ERROR`, `Traceback`, `CRITICAL`
- Runs `uv run poe lint` and `uv run poe typecheck`
- Runs `uv run poe test`
- Writes a report to `/tmp/bug-report.json`

### Phase 3 — Parse & fix

Read `/tmp/bug-report.json` and identify:

| Signal | What it means |
|--------|--------------|
| `HTTP 500` | Server-side crash — traceback in server log |
| `HTTP 404` | Missing route or static asset |
| `console.error` | JS runtime error |
| `lint_error` | Code style / import issue |
| `type_error` | mypy type violation |
| `test_failure` | pytest regression |

For each bug:
1. Read the error message and location
2. Find the relevant source file
3. Fix the root cause (minimum diff)
4. If unsure, add a `# ponytail: <why>` comment so the shortcut is tracked

### Phase 4 — Re-verify

After fixing all bugs from the current report:
1. Kill and restart the server
2. Re-run the test script
3. Check the new report
4. If new bugs appear (or old ones remain), loop back to Phase 3
5. If clean, report success and exit

## Rules

- Fix every bug you find, no matter how small (console warnings, missing alt text, 404 favicon)
- Never leave a broken page — if you can't fix a server crash, at least make it fail gracefully
- One fix per bug, smallest diff possible
- Track deliberate shortcuts with `ponytail:` comments
- Stop only when the report shows zero errors across all categories
