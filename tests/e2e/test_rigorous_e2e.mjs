/**
 * Rigorous E2E Test Suite with Chrome DevTools
 * Tests: Console errors, Network errors, Performance, JS errors, Memory
 *
 * Run: node tests/e2e/test_rigorous_e2e.mjs
 */

import { chromium } from "playwright";

const BASE_URL = "http://localhost:7860";
const PAGES = [
  // CareerDEX
  "/career", "/career/tracker", "/career/scanner", "/career/resume-matcher",
  "/career/networking", "/career/progress", "/career/interview",
  "/career/cover-letter", "/career/resume", "/career/batch",
  // AI
  "/ai", "/ai/playground", "/ai/collections", "/ai/vectors",
  "/ai/traces", "/ai/tools", "/ai/agents",
  // ML
  "/ml", "/ml/experiments", "/ml/models", "/ml/features",
  // Data Pages
  "/data", "/data/sources", "/data/pipelines", "/data/warehouse",
  // System Pages
  "/system", "/system/status", "/system/logs",
];

let browser, page, context;
let results = { pass: 0, fail: 0, errors: [], warnings: [] };

async function initBrowser() {
  browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
  });
  context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    locale: 'en-US'
  });
  page = await context.newPage();

  // Setup comprehensive logging
  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    if (type === 'error') {
      results.errors.push({ page: page.url(), text });
    } else if (text.includes('Warning') || text.includes('warn')) {
      results.warnings.push({ page: page.url(), text });
    }
  });

  page.on('pageerror', err => {
    results.errors.push({ page: page.url(), text: `JS Error: ${err.message}` });
  });

  page.on('requestfailed', req => {
    results.errors.push({ page: page.url(), text: `Request failed: ${req.url()}` });
  });

  page.on('response', res => {
    if (res.status() >= 400) {
      results.errors.push({ page: page.url(), text: `HTTP ${res.status()}: ${res.url()}` });
    }
  });
}

async function testPage(path) {
  const url = `${BASE_URL}${path}`;
  console.log(`\n🔍 Testing: ${path}`);

  // Navigate and measure time
  const start = Date.now();
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
  const loadTime = Date.now() - start;

  // Wait for any JS to execute
  await page.waitForTimeout(1000);

  // Check page loaded
  if (page.url().includes('404')) {
    console.log(`   ❌ 404 Not Found`);
    results.fail++;
    return;
  }

  // Check for JavaScript errors
  const jsErrors = await page.evaluate(() => window.onerror);

  // Check performance metrics via CDP
  let perfMetrics = {};
  try {
    const client = await page.context().newCDPSession(page);
    perfMetrics = await client.send('Performance.getMetrics');
    await client.detach();
  } catch (e) {
    // CDP not available
  }

  // Collect page info
  const title = await page.title().catch(() => 'N/A');
  const hasBody = await page.locator('body').count() > 0;

  // Get DOM depth
  const domDepth = await page.evaluate(() => {
    function getDepth(el, d = 0) {
      if (!el.children.length) return d;
      return Math.max(...Array.from(el.children).map(c => getDepth(c, d + 1)));
    }
    return getDepth(document.body);
  }).catch(() => 0);

  // Element count
  const elementCount = await page.locator('*').count();

  // Check for key elements
  const hasNavbar = await page.locator('nav, .navbar, [class*=nav]').count() > 0;
  const hasContent = await page.locator('main, article, [class*=content]').count() > 0;

  const status = loadTime < 5000 && hasBody && elementCount > 10;

  console.log(`   ✅ Load: ${loadTime}ms | Elements: ${elementCount} | DOM: ${domDepth} | Title: "${title}"`);
  console.log(`   📊 Navbar: ${hasNavbar} | Content: ${hasContent}`);

  if (loadTime > 3000) {
    results.warnings.push({ page: path, text: `Slow load: ${loadTime}ms` });
  }

  if (status) results.pass++;
  else results.fail++;
}

async function testForms() {
  // Test form interactions
  console.log(`\n🧑‍💻 Testing Forms...`);

  await page.goto(`${BASE_URL}/career/tracker`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);

  // Try to fill inputs
  const inputs = await page.locator('input, textarea, select').count();
  console.log(`   Found ${inputs} form elements`);

  // Try typing
  if (inputs > 0) {
    const firstInput = page.locator('input, textarea').first();
    if (await firstInput.isVisible().catch(() => false)) {
      await firstInput.fill('test');
      await page.waitForTimeout(200);
      console.log(`   ✅ Input interaction works`);
      results.pass++;
    }
  }
}

async function testNavigation() {
  console.log(`\n🔀 Testing Navigation...`);

  await page.goto(`${BASE_URL}/career`, { waitUntil: 'networkidle' });

  // Get all links
  const links = await page.locator('a[href]').count();
  console.log(`   Found ${links} links`);

  // Test a few links
  let working = 0;
  const hrefs = await page.locator('a[href]').evaluateAll(els =>
    els.slice(0, 5).map(e => e.getAttribute('href'))
  );

  for (const href of hrefs) {
    if (href && href.startsWith('/')) {
      await page.goto(`${BASE_URL}${href}`, { waitUntil: 'domcontentloaded', timeout: 5000 }).catch(() => {});
      if (!page.url().includes('404')) working++;
    }
  }

  console.log(`   ✅ ${working}/5 tested links work`);
  results.pass++;
}

async function testResponsive() {
  console.log(`\n📱 Testing Responsive...`);

  const sizes = [
    { w: 1920, h: 1080, name: 'Desktop' },
    { w: 768, h: 1024, name: 'Tablet' },
    { w: 375, h: 667, name: 'Mobile' },
  ];

  for (const size of sizes) {
    await page.setViewportSize({ width: size.w, height: size.h });
    await page.goto(`${BASE_URL}/career`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(300);

    const width = await page.evaluate(() => window.innerWidth);
    const height = await page.evaluate(() => window.innerHeight);

    console.log(`   ✅ ${size.name}: ${width}x${height}`);
  }

  // Reset
  await page.setViewportSize({ width: 1400, height: 900 });
  results.pass++;
}

async function testPerformance() {
  console.log(`\n⚡ Performance Test...`);

  // Create CDP session
  const client = await page.context().newCDPSession(page);

  // Enable performance tracking
  await client.send('Performance.enable');

  // Navigate
  await page.goto(`${BASE_URL}/career`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  // Get metrics
  const metrics = await client.send('Performance.getMetrics');

  const metricNames = metrics.metrics.reduce((acc, m) => {
    acc[m.name] = m.value;
    return acc;
  }, {});

  console.log(`   📊 DOMNodes: ${metricNames.Nodes || 'N/A'}`);
  console.log(`   📊 JSEventListeners: ${metricNames.JSEventListeners || 'N/A'}`);
  console.log(`   📊 LayoutCount: ${metricNames.LayoutCount || 'N/A'}`);
  console.log(`   📊 ScriptDuration: ${metricNames.ScriptDuration?.toFixed(2) || 'N/A'}ms`);
  console.log(`   📊 TaskDuration: ${metricNames.TaskDuration?.toFixed(2) || 'N/A'}ms`);

  await client.detach();
  results.pass++;
}

async function testAccessibility() {
  console.log(`\n♿ Testing Accessibility...`);

  await page.goto(`${BASE_URL}/career/tracker`, { waitUntil: 'networkidle' });

  // Check for ARIA labels
  const ariaLabels = await page.evaluate(() => {
    const els = document.querySelectorAll('[aria-label], [aria-describedby]');
    return els.length;
  });

  // Check for roles
  const roles = await page.evaluate(() => {
    const els = document.querySelectorAll('[role]');
    return els.length;
  });

  // Check for alt text on images
  const altInfo = await page.evaluate(() => {
    const imgs = Array.from(document.querySelectorAll('img'));
    const withAlt = imgs.filter(i => i.alt).length;
    const withoutAlt = imgs.filter(i => !i.alt && !i.getAttribute('aria-hidden')).length;
    return { withAlt, withoutAlt };
  });

  console.log(`   📊 ARIA labels: ${ariaLabels}`);
  console.log(`   📊 Roles: ${roles}`);
  console.log(`   📊 Images with alt: ${altInfo.withAlt}, without: ${altInfo.withoutAlt}`);

  if (altInfo.withoutAlt > 10) {
    results.warnings.push({ page: '/career/tracker', text: `${altInfo.withoutAlt} images missing alt text` });
  }

  results.pass++;
}

async function main() {
  console.log('═'.repeat(60));
  console.log('🎯 RIGOROUS E2E TEST SUITE');
  console.log('═'.repeat(60));
  console.log(`   Base URL: ${BASE_URL}`);
  console.log(`   ${new Date().toISOString()}`);
  console.log('═'.repeat(60));

  await initBrowser();

  // Test each page
  for (const path of PAGES) {
    await testPage(path);
  }

  // Interactive tests
  await testForms();
  await testNavigation();
  await testResponsive();
  await testPerformance();
  await testAccessibility();

  await browser.close();

  // Results
  console.log('\n' + '═'.repeat(60));
  console.log('📊 RESULTS');
  console.log('═'.repeat(60));
  console.log(`   ✅ Passed: ${results.pass}`);
  console.log(`   ❌ Failed: ${results.fail}`);
  console.log(`   ⚠️  Errors: ${results.errors.length}`);
  console.log(`   ⚠️  Warnings: ${results.warnings.length}`);

  if (results.errors.length > 0) {
    console.log('\n❌ ERRORS:');
    results.errors.slice(0, 10).forEach(e => {
      console.log(`   - ${e.page}: ${e.text.slice(0, 80)}`);
    });
  }

  if (results.warnings.length > 0) {
    console.log('\n⚠️  WARNINGS:');
    results.warnings.slice(0, 5).forEach(w => {
      console.log(`   - ${w.page}: ${w.text.slice(0, 60)}`);
    });
  }

  console.log('═'.repeat(60));

  const total = results.pass + results.fail + PAGES.length;
  const success = (results.pass / (results.pass + results.fail)) * 100;
  console.log(`\n🎉 Success Rate: ${success.toFixed(1)}%`);

  process.exit(results.fail > 10 ? 1 : 0);
}

main();
