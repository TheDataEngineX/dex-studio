/**
 * E2E Test Suite - All Modules
 */

import { chromium } from "playwright";

const BASE_URL = "http://localhost:7860";
let browser, page;

async function init() {
  browser = await chromium.launch({ headless: true });
  page = await browser.newContext({ viewport: { width: 1400, height: 900 } }).then(c => c.newPage());
}

async function check(path) {
  await page.goto(`${BASE_URL}${path}`, { waitUntil: "domcontentloaded", timeout: 15000 });
  return !page.url().includes("404");
}

async function main() {
  await init();

  const routes = [
    // CareerDEX
    "/career", "/career/tracker", "/career/scanner", "/career/resume-matcher",
    "/career/networking", "/career/progress", "/career/interview", "/career/cover-letter",
    "/career/resume", "/career/batch", "/career/projects", "/career/stories",
    "/career/negotiate", "/career/apply",
    // AI Pages
    "/ai", "/ai/dashboard", "/ai/playground", "/ai/collections",
    "/ai/vectors", "/ai/traces", "/ai/tools", "/ai/agents",
    // ML Pages
    "/ml", "/ml/dashboard", "/ml/experiments", "/ml/models",
    "/ml/features", "/ml/predictions",
    // Data Pages
    "/data", "/data/dashboard", "/data/sources", "/data/pipelines",
    "/data/warehouse", "/data/catalog",
    // System Pages
    "/system", "/system/status", "/system/logs", "/system/metrics",
  ];

  let passed = 0, failed = 0;

  for (const path of routes) {
    const ok = await check(path).catch(() => false);
    if (ok) {
      console.log(`✅ ${path}`);
      passed++;
    } else {
      console.log(`❌ ${path}`);
      failed++;
    }
  }

  console.log(`\n📊 ${passed}/${passed+failed} pages pass`);
  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

main();
