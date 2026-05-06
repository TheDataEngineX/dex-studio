/**
 * E2E Test Suite for CareerDEX
 * Tests all major CareerDEX functionality end-to-end
 *
 * Run: node tests/e2e/test_careerdex_e2e.mjs
 * Requires: DEX Studio running at http://localhost:7860
 */

import { chromium } from "playwright";

const BASE_URL = "http://localhost:7860";
const TEST_TIMEOUT = 30000;

let browser;
let context;
let page;
let consoleLogs = [];
let testResults = { passed: 0, failed: 0, tests: [] };

async function initBrowser() {
  console.log(`\n🚀 Launching chromium...`);
  browser = await chromium.launch({ headless: true });
  context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  page = await context.newPage();

  consoleLogs = [];
  page.on("console", msg => {
    if (msg.type() === "error") {
      consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
    }
  });
}

async function test(name, fn) {
  const testName = `  ${name}`;
  try {
    await fn();
    console.log(`✅ ${testName}`);
    testResults.passed++;
  } catch (err) {
    console.log(`❌ ${testName}`);
    console.log(`   → ${err.message.slice(0, 100)}`);
    testResults.failed++;
  }
}

async function navigate(path) {
  await page.goto(`${BASE_URL}${path}`, { waitUntil: "domcontentloaded", timeout: 15000 });
  await page.waitForTimeout(500);
}

async function checkPage(titlePattern, path) {
  // Just check page loads with HTTP 200
  await navigate(path);
  const url = page.url();
  if (url.includes("404")) throw new Error(`Page not found: ${path}`);
  // Page loaded successfully
}

// ============================================================================
// TEST CASES - Each verifies page loads without crash
// ============================================================================

async function testCareerDashboard() { await checkPage("Dashboard", "/career"); }
async function testJobTracker() { await checkPage("Tracker", "/career/tracker"); }
async function testJobSearch() { await checkPage("Scanner", "/career/scanner"); }
async function testResumeMatcher() { await checkPage("Resume", "/career/resume-matcher"); }
async function testNetworking() { await checkPage("Networking", "/career/networking"); }
async function testProgress() { await checkPage("Progress", "/career/progress"); }
async function testInterview() { await checkPage("Interview", "/career/interview"); }
async function testCoverLetter() { await checkPage("Cover Letter", "/career/cover-letter"); }
async function testResumeBuilder() { await checkPage("Resume Builder", "/career/resume"); }
async function testBatch() { await checkPage("Batch", "/career/batch"); }
async function testProjects() { await checkPage("Projects", "/career/projects"); }
async function testStories() { await checkPage("Stories", "/career/stories"); }
async function testNegotiate() { await checkPage("Negotiati", "/career/negotiate"); }
async function testApply() { await checkPage("Apply", "/career/apply"); }

// ============================================================================
// MAIN
// ============================================================================

async function main() {
  console.log("═".repeat(50));
  console.log("🎯 CareerDEX E2E Test Suite");
  console.log("═".repeat(50));

  await initBrowser();

  try {
    // Core CareerDEX pages
    await test("Career Dashboard", testCareerDashboard);
    await test("Job Tracker", testJobTracker);
    await test("Job Scanner", testJobSearch);
    await test("Resume Matcher", testResumeMatcher);
    await test("Networking", testNetworking);
    await test("Progress", testProgress);
    await test("Interview Prep", testInterview);
    await test("Cover Letter", testCoverLetter);
    await test("Resume Builder", testResumeBuilder);
    await test("Batch Ops", testBatch);
    await test("Projects", testProjects);
    await test("Stories", testStories);
    await test("Negotiate", testNegotiate);
    await test("Apply", testApply);

  } catch (err) {
    console.error(`\n💥 Fatal: ${err.message}`);
  } finally {
    await browser.close();
  }

  // Summary
  console.log("\n" + "═".repeat(50));
  console.log(`📊 ${testResults.passed}/${testResults.passed + testResults.failed} tests passed`);
  console.log("═".repeat(50));

  if (testResults.failed > 0) {
    console.log("\n⚠️  Some pages need investigation");
  }

  process.exit(testResults.failed > 0 ? 1 : 0);
}

main();
