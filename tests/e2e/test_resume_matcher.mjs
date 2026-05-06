/**
 * E2E test: Resume Matcher page — verify Analyze Match produces visible output.
 *
 * Uses "Use saved resume" mode (fast path, no Ollama parse needed).
 * Requires DEX Studio at http://localhost:7860 and a saved resume at
 * ~/.dex-studio/careerdex/resume.json (created by seed script or Resume Builder).
 */

import { chromium } from "playwright";

const BASE_URL = "http://localhost:7860";
const JOB_DESC = `
Senior Data Engineer — Remote

Required skills:
- Python (5+ years)
- SQL / PostgreSQL
- Data pipelines (Airflow, dbt)
- Cloud platforms: AWS or GCP
- Docker, Kubernetes
- Git, GitHub Actions
- FastAPI / REST API experience
`;

const RESULT_SELECTORS = [
  "text=Overall Match",
  "text=Matched Skills",
  "text=Missing Skills",
];

async function fillJD(page) {
  // textarea[1] has placeholder "Paste the job description here..."
  const jdTA = page.locator("textarea").nth(1);
  await jdTA.waitFor({ timeout: 5000 });
  await jdTA.fill(JOB_DESC);
  // Tab away to trigger NiceGUI/Vue value sync via WebSocket
  await jdTA.press("Tab");
  await page.waitForTimeout(800);
}

async function waitForResult(page) {
  for (const selector of RESULT_SELECTORS) {
    const el = page.locator(selector).first();
    if (await el.isVisible({ timeout: 25000 }).catch(() => false)) {
      const text = await el.textContent().catch(() => "");
      console.log(`   Found: "${selector}" → "${text}"`);
      return true;
    }
  }
  return false;
}

async function dumpDebugInfo(page, consoleLogs) {
  const bodyText = await page.locator("body").innerText().catch(() => "");
  console.log("\n--- Page text ---");
  console.log(bodyText.slice(0, 3000));
  if (consoleLogs.length) {
    console.log("\n--- Browser console ---");
    consoleLogs.forEach(l => console.log(l));
  }
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();

const consoleLogs = [];
page.on("console", msg => consoleLogs.push(`[${msg.type()}] ${msg.text()}`));

try {
  console.log("1. Loading resume matcher page...");
  await page.goto(`${BASE_URL}/career/resume-matcher`, { waitUntil: "networkidle", timeout: 30000 });
  await page.screenshot({ path: "/tmp/rm_01_loaded.png" });

  const title = await page.locator("text=Resume Matcher").first().textContent();
  const badge = await page.locator(".q-badge").first().textContent({ timeout: 5000 }).catch(() => "N/A");
  console.log(`   Title: "${title}" | Ollama: "${badge}"`);

  // Verify saved resume is loaded (page should show the name, not "No saved resume found")
  const noResumeMsg = page.locator("text=No saved resume found");
  const hasSavedResume = !(await noResumeMsg.isVisible({ timeout: 2000 }).catch(() => false));
  console.log(`   Saved resume loaded: ${hasSavedResume}`);
  if (!hasSavedResume) {
    throw new Error("No saved resume found — seed ~/.dex-studio/careerdex/resume.json first");
  }
  await page.screenshot({ path: "/tmp/rm_02_saved_resume.png" });

  console.log("2. Filling job description...");
  await fillJD(page);
  await page.screenshot({ path: "/tmp/rm_03_filled.png" });

  console.log("3. Clicking Analyze Match...");
  const analyzeBtn = page.locator("button", { hasText: "Analyze Match" });
  await analyzeBtn.waitFor({ timeout: 5000 });
  await analyzeBtn.click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "/tmp/rm_04_after_click.png" });

  console.log("4. Waiting for match result...");
  const found = await waitForResult(page);
  await page.screenshot({ path: "/tmp/rm_05_result.png" });

  if (!found) {
    await dumpDebugInfo(page, consoleLogs);
    throw new Error("No result indicators found after Analyze Match click");
  }

  // Extract and log score
  const scoreBadge = page.locator(".q-badge").filter({ hasText: /\d+%/ }).first();
  const score = await scoreBadge.textContent({ timeout: 5000 }).catch(() => "N/A");

  await page.locator("text=Matched Skills").first().waitFor({ timeout: 5000 });
  await page.locator("text=Missing Skills").first().waitFor({ timeout: 5000 });

  // Collect visible skill badges from results area
  const skillBadges = page.locator(".q-badge").filter({ hasText: /^(?!\d+%).+/ });
  const badgeCount = await skillBadges.count();

  console.log(`   Score: ${score}`);
  console.log(`   Skill badges rendered: ${badgeCount}`);

  console.log("\n✓ PASSED — Analyze Match produces complete result in UI");
  console.log("  Screenshots saved to /tmp/rm_0{1-5}.png");
} catch (err) {
  console.error(`\n✗ FAILED: ${err.message}`);
  await page.screenshot({ path: "/tmp/rm_error.png", fullPage: true }).catch(() => {});
  process.exit(1);
} finally {
  await browser.close();
}
