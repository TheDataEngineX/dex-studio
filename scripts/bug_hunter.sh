#!/usr/bin/env bash
set -euo pipefail

# Bug Hunter — Self-Healing QA Runner
# Orchestrates: server start → Playwright crawl → server log scan → lint/typecheck/test
# Output: /tmp/bug-report.json

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HEADLESS="${1:---headless}"
export REPORT_FILE="/tmp/bug-report.json"
export SERVER_LOG="/tmp/dex-server-bh.log"
export BUG_LOG="/tmp/dex-bugs.log"
export PLAYWRIGHT_HTML_REPORT="/tmp/bug-report-playwright"

echo '{"http_errors":[],"console_errors":[],"server_tracebacks":[],"lint_errors":[],"type_errors":[],"test_failures":[],"summary":""}' > "$REPORT_FILE"
: > "$BUG_LOG"

# ── Helpers ──────────────────────────────────────────────────────────────────
fail() { echo "FAIL: $*" >> "$BUG_LOG"; }
ok()   { echo "OK:   $*" >> "$BUG_LOG"; }

# ── Phase 1: Start server ────────────────────────────────────────────────────
kill_server() {
  pkill -f "dex-studio" 2>/dev/null || true
  pkill -f uvicorn 2>/dev/null || true
  sleep 1
}

kill_server
rm -f "$SERVER_LOG"
rm -f "$HOME/.dex-studio/auth.hash"

echo "Starting dex-studio server..."
uv run dex-studio --port 7860 > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!

# Wait for server to be ready
for i in $(seq 1 30); do
  if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7860/ 2>/dev/null | grep -q "303\|200"; then
    ok "server started (PID $SERVER_PID)"
    break
  fi
  if [ "$i" -eq 30 ]; then
    fail "server failed to start within 30s"
    exit 1
  fi
  sleep 1
done

# ── Phase 2: Run Playwright tests ────────────────────────────────────────────
echo "Running Playwright route checks..."
mkdir -p "$PLAYWRIGHT_HTML_REPORT"

# Generate a temporary Node.js script for the Playwright crawl
cat > /tmp/bug-crawl.mjs << 'SCRIPT'
import { chromium } from "playwright";
import { readFileSync, writeFileSync } from "fs";

const BASE = "http://127.0.0.1:7860";
const BRAVE = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser";

const ROUTES = [
  // Setup / Auth
  { path: "/setup", auth: false },
  { path: "/login", auth: false },
  // Hub
  { path: "/", auth: true },
  { path: "/onboarding", auth: false },
  // Data domain
  { path: "/data/sources", auth: true },
  { path: "/data/pipelines", auth: true },
  { path: "/data/pipelines/bronze_titles", auth: true },
  { path: "/data/pipelines/bronze_titles/quality", auth: true },
  { path: "/data/catalog", auth: true },
  { path: "/data/warehouse", auth: true },
  { path: "/data/sql", auth: true },
  { path: "/data/lineage", auth: true },
  { path: "/data/quality", auth: true },
  { path: "/data/schema", auth: true },
  { path: "/data/transforms", auth: true },
  { path: "/data/streaming", auth: true },
  { path: "/data/watermarks", auth: true },
  { path: "/data/backfill", auth: true },
  { path: "/data/pipelines/runs", auth: true },
  { path: "/data/dashboard", auth: true },
  // Intelligence domain
  { path: "/intelligence/dashboard", auth: true },
  { path: "/intelligence/playground", auth: true },
  { path: "/intelligence/models", auth: true },
  { path: "/intelligence/experiments", auth: true },
  { path: "/intelligence/features", auth: true },
  { path: "/intelligence/predictions", auth: true },
  { path: "/intelligence/drift", auth: true },
  { path: "/intelligence/agents", auth: true },
  { path: "/intelligence/tools", auth: true },
  { path: "/intelligence/traces", auth: true },
  { path: "/intelligence/embeddings", auth: true },
  { path: "/intelligence/finetune", auth: true },
  // SecOps domain
  { path: "/secops", auth: true },
  { path: "/secops/privacy", auth: true },
  { path: "/secops/policies", auth: true },
  { path: "/secops/audit", auth: true },
  { path: "/secops/alerts", auth: true },
  // System domain
  { path: "/system/status", auth: true },
  { path: "/system/components", auth: true },
  { path: "/system/logs", auth: true },
  { path: "/system/compaction", auth: true },
  { path: "/system/scheduler", auth: true },
  { path: "/system/runs", auth: true },
  { path: "/system/alerting", auth: true },
  { path: "/system/costs", auth: true },
  { path: "/system/settings", auth: true },
  // API
  { path: "/api/pipelines", auth: true },
  { path: "/api/alerts", auth: true },
  { path: "/api/quality/contracts", auth: true },
];

const errors = { http_errors: [], console_errors: [] };

async function main() {
  // First navigate to /setup, create password, login to get session
  const browser = await chromium.launch({
    executablePath: BRAVE,
    headless: process.argv.includes("--headless") ? true : false,
    args: ["--no-sandbox"],
  });
  const ctx = await browser.newContext({ viewport: { width: 1440, 900 } });
  const page = await ctx.newPage();

  // Listen for console errors
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      errors.console_errors.push({
        text: msg.text(),
        location: msg.location(),
      });
    }
  });
  page.on("pageerror", (err) => {
    errors.console_errors.push({ text: err.message, stack: err.stack });
  });
  page.on("response", (resp) => {
    const status = resp.status();
    if (status >= 400) {
      errors.http_errors.push({
        url: resp.url(),
        status,
        method: resp.request().method(),
      });
    }
  });

  // Auth setup
  await page.goto(BASE + "/setup", { waitUntil: "load", timeout: 10000 });
  await page.fill('input[name="password"]', "bugdemo123");
  await page.click('button[type="submit"]');
  await page.waitForTimeout(1000);

  // Login
  await page.goto(BASE + "/login", { waitUntil: "load", timeout: 10000 });
  await page.fill('input[name="passphrase"]', "bugdemo123");
  await page.click('button[type="submit"]');
  await page.waitForURL("**/", { timeout: 10000 });
  await page.waitForTimeout(500);

  // Visit every route
  for (const route of ROUTES) {
    try {
      const resp = await page.goto(BASE + route.path, {
        waitUntil: "load",
        timeout: 15000,
      });
      const status = resp ? resp.status() : 0;
      if (status >= 400) {
        errors.http_errors.push({
          url: route.path,
          status,
          method: "GET",
        });
      }
    } catch (e) {
      errors.http_errors.push({
        url: route.path,
        status: 0,
        error: e.message,
      });
    }
    await page.waitForTimeout(200);
  }

  await browser.close();
  writeFileSync("/tmp/bug-crawl-results.json", JSON.stringify(errors));
  console.log(`Crawl complete: ${errors.http_errors.length} HTTP errors, ${errors.console_errors.length} console errors`);
}

main().catch((e) => {
  writeFileSync("/tmp/bug-crawl-results.json", JSON.stringify({
    http_errors: [{ url: "fatal", status: 0, error: e.message }],
    console_errors: [{ text: e.message, stack: e.stack }],
  }));
  process.exit(1);
});
SCRIPT

node /tmp/bug-crawl.mjs "$HEADLESS" 2>/dev/null || true

# Merge Playwright results into report
if [ -f /tmp/bug-crawl-results.json ]; then
  PW_ERRORS=$(cat /tmp/bug-crawl-results.json)
  HTTP_COUNT=$(echo "$PW_ERRORS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['http_errors']))")
  CONSOLE_COUNT=$(echo "$PW_ERRORS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['console_errors']))")
  echo "$HTTP_COUNT HTTP errors, $CONSOLE_COUNT console errors" >> "$BUG_LOG"

  for err in $(seq 0 $((HTTP_COUNT - 1))); do
    URL=$(echo "$PW_ERRORS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['http_errors'][$err].get('url',''))")
    STATUS=$(echo "$PW_ERRORS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['http_errors'][$err].get('status',0))")
    if [ "$URL" != "" ]; then
      fail "HTTP $STATUS $URL"
    fi
  done
else
  PW_ERRORS='{"http_errors":[],"console_errors":[]}'
fi

# ── Phase 3: Scan server logs ────────────────────────────────────────────────
echo "Scanning server logs..."
TRACEBACKS=$(grep -n "Traceback\|ERROR\|CRITICAL" "$SERVER_LOG" 2>/dev/null || true)
if [ -n "$TRACEBACKS" ]; then
  echo "Server tracebacks found:" >> "$BUG_LOG"
  echo "$TRACEBACKS" >> "$BUG_LOG"
fi
TRACE_COUNT=$(echo "$TRACEBACKS" | grep -c "Traceback" 2>/dev/null) || TRACE_COUNT=0

# ── Phase 4: Lint ────────────────────────────────────────────────────────────
echo "Running lint..."
LINT_OUTPUT=$(uv run poe lint 2>&1 || true)
if echo "$LINT_OUTPUT" | grep -q "error"; then
  echo "Lint errors:" >> "$BUG_LOG"
  echo "$LINT_OUTPUT" | grep -i "error" >> "$BUG_LOG" || true
fi
LINT_ERRORS=$(echo "$LINT_OUTPUT" | grep -c "^.*error" 2>/dev/null) || LINT_ERRORS=0

# ── Phase 5: Typecheck ──────────────────────────────────────────────────────
echo "Running typecheck..."
TYPE_OUTPUT=$(uv run poe typecheck 2>&1 || true)
if echo "$TYPE_OUTPUT" | grep -q "error"; then
  echo "Type errors:" >> "$BUG_LOG"
  echo "$TYPE_OUTPUT" | grep "error" >> "$BUG_LOG" || true
fi
TYPE_ERRORS=$(echo "$TYPE_OUTPUT" | grep -c "error" 2>/dev/null) || TYPE_ERRORS=0

# ── Phase 6: Tests ──────────────────────────────────────────────────────────
echo "Running tests..."
TEST_OUTPUT=$(uv run poe test 2>&1 || true)
TEST_FAILS=0
if echo "$TEST_OUTPUT" | grep -q "FAILED"; then
  TEST_FAILS=$(echo "$TEST_OUTPUT" | grep -c "FAILED" 2>/dev/null || echo 1)
  echo "Test failures:" >> "$BUG_LOG"
  echo "$TEST_OUTPUT" | grep "FAILED" >> "$BUG_LOG" || true
fi

# ── Phase 7: Build final report ──────────────────────────────────────────────
cat > /tmp/build_report.py << 'PYEOF'
import json, os

pw_file = '/tmp/bug-crawl-results.json'
pw = json.load(open(pw_file)) if os.path.exists(pw_file) else {'http_errors':[],'console_errors':[]}

tc = int(os.environ.get('TRACE_COUNT', '0'))
le = int(os.environ.get('LINT_ERRORS', '0'))
te = int(os.environ.get('TYPE_ERRORS', '0'))
tf = int(os.environ.get('TEST_FAILS', '0'))

total = len(pw.get('http_errors',[])) + len(pw.get('console_errors',[])) + tc + le + te + tf

report = {
    'http_errors': pw.get('http_errors', []),
    'console_errors': pw.get('console_errors', []),
    'server_tracebacks': tc,
    'lint_errors': le,
    'type_errors': te,
    'test_failures': tf,
    'summary': {
        'total_http_errors': len(pw.get('http_errors', [])),
        'total_console_errors': len(pw.get('console_errors', [])),
        'total_server_tracebacks': tc,
        'total_lint_errors': le,
        'total_type_errors': te,
        'total_test_failures': tf,
        'status': 'PASS' if total == 0 else 'FAIL'
    }
}
with open('/tmp/bug-report.json', 'w') as f:
    json.dump(report, f, indent=2)
print(json.dumps(report['summary']))
PYEOF
export TRACE_COUNT LINT_ERRORS TYPE_ERRORS TEST_FAILS
python3 /tmp/build_report.py

# ── Kill server ──────────────────────────────────────────────────────────────
kill_server

echo ""
python3 -c "
import json
d=json.load(open('/tmp/bug-report.json'))
s=d['summary']
print('╔══════════════════════════════════════╗')
print('║         Bug Hunt Summary             ║')
print('╠══════════════════════════════════════╣')
print(f'║ HTTP errors:     {str(s[\"total_http_errors\"]):>4}                    ║')
print(f'║ Console errors:  {str(s[\"total_console_errors\"]):>4}                    ║')
print(f'║ Server crashes:  {str(s[\"total_server_tracebacks\"]):>4}                    ║')
print(f'║ Lint errors:     {str(s[\"total_lint_errors\"]):>4}                    ║')
print(f'║ Type errors:     {str(s[\"total_type_errors\"]):>4}                    ║')
print(f'║ Test failures:   {str(s[\"total_test_failures\"]):>4}                    ║')
print(f'║──────────────────────────────────────╣')
print(f'║ Status:          {s[\"status\"]:<4}                       ║')
print('╚══════════════════════════════════════╝')
"
echo ""
echo "Full report: /tmp/bug-report.json"
echo "Bug log:     $BUG_LOG"
echo "Server log:  $SERVER_LOG"
