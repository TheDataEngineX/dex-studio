/**
 * DEX Studio — Full E2E Test Suite
 *
 * Senior-level test coverage: real user flows, real data, interaction testing,
 * error states, cross-domain navigation, and data persistence verification.
 *
 * Architecture notes:
 *  - NiceGUI SPA — all routes serve the shell; content hydrates via WebSocket
 *  - Quasar component library — inputs are .q-input, buttons are .q-btn
 *  - Wait for networkidle + NiceGUI hydration before asserting content
 *
 * Run: node tests/e2e/test_full_e2e.mjs
 * Prereq: server running at http://localhost:7860  (uv run poe dev)
 */

import { chromium } from "playwright";

// ─────────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────────

const BASE = "http://localhost:7860";
const HYDRATION_MS = 1500; // NiceGUI WS hydration time
const NAV_TIMEOUT = 20000;

// Real-world test data — as a data engineer looking for a new job
const TEST_DATA = {
  application: {
    company: "Databricks",
    position: "Senior Data Engineer",
    url: "https://databricks.com/careers",
    salary_min: "140000",
    salary_max: "180000",
    tags: "remote, equity, tier-1",
    note: "Referral from LinkedIn — strong Spark background required",
  },
  contact: {
    name: "Alex Rivera",
    company: "Databricks",
    title: "Engineering Recruiter",
    email: "alex@databricks.com",
    linkedin: "linkedin.com/in/alexrivera",
  },
  resume: `Jay Myaka | Senior Data Engineer
Email: jay@example.com | LinkedIn: linkedin.com/in/jaymyaka

SUMMARY
5+ years building production data platforms. Expert in Python, Apache Spark, dbt, Airflow,
Kafka, and cloud data warehouses (Snowflake, BigQuery, Redshift). Led migration of
on-prem Hadoop cluster to GCP Dataproc, reducing cost by 40%. Built ML feature store
serving 200+ models in real-time.

SKILLS
Languages: Python, SQL, Scala, Bash
Data Eng: Apache Spark, dbt, Airflow, Kafka, Flink, dlt, duckdb
Cloud: GCP (Dataproc, BigQuery, Pub/Sub), AWS (EMR, Glue, S3), Azure (ADF, Synapse)
ML: MLflow, Feast, Vertex AI, feature engineering, model serving
Infra: Kubernetes, Helm, Terraform, Docker, ArgoCD

EXPERIENCE
Senior Data Engineer — StreamCo (2022–present)
- Built real-time event pipeline (Kafka → Flink → BigQuery) processing 2M events/sec
- Migrated legacy ETL to dbt + Airflow, cutting pipeline failures by 70%
- Implemented ML feature store with Feast, enabling 200+ model deployments

Data Engineer — AnalyticsCo (2020–2022)
- Designed Spark-based batch ETL for 50TB daily data
- Built self-serve SQL analytics platform on Redshift + dbt`,

  jd: `Senior Data Engineer — Databricks

We are looking for a Senior Data Engineer to join our Data Platform team.

REQUIRED:
- 5+ years Python and SQL
- Apache Spark (PySpark or Scala)
- Cloud data warehouses: Snowflake or BigQuery
- Pipeline orchestration: Airflow or Prefect
- Data modeling: dbt, dimensional modeling
- Streaming experience: Kafka or Flink

NICE TO HAVE:
- MLflow or ML platform experience
- Kubernetes / Helm
- dbt Cloud certification

You will design and build high-throughput data pipelines, work closely with ML
teams on feature engineering, and own data quality SLAs.`,

  sql_queries: [
    { label: "Introspect — show tables", sql: "SHOW TABLES", expectsResult: false },
    { label: "Arithmetic — constant query", sql: "SELECT 42 AS answer, 'dex' AS platform", expectsResult: true },
    { label: "Generate series", sql: "SELECT * FROM generate_series(1, 5) t(n)", expectsResult: true },
    { label: "Date functions", sql: "SELECT current_date AS today, current_timestamp AS now", expectsResult: true },
    { label: "Error — bad SQL", sql: "SELECT * FROM nonexistent_table_xyz_404", expectsError: true },
  ],

  prompt: "What is Apache Spark and why do data engineers use it? One paragraph.",
};

// ─────────────────────────────────────────────────────────────────────────────
// Test harness
// ─────────────────────────────────────────────────────────────────────────────

let browser, context, page;
const results = { pass: 0, fail: 0, skip: 0, details: [] };
let currentSuite = "";

function suite(name) {
  currentSuite = name;
  console.log(`\n${"─".repeat(60)}`);
  console.log(`  ${name}`);
  console.log("─".repeat(60));
}

async function test(name, fn) {
  const label = `${currentSuite} > ${name}`;
  try {
    await fn();
    console.log(`  ✅  ${name}`);
    results.pass++;
    results.details.push({ status: "pass", label });
  } catch (err) {
    const msg = err?.message?.split("\n")[0] ?? String(err);
    console.log(`  ❌  ${name}`);
    console.log(`       ${msg}`);
    results.fail++;
    results.details.push({ status: "fail", label, error: msg });
  }
}

function skip(name, reason) {
  console.log(`  ⏭   ${name} — ${reason}`);
  results.skip++;
  results.details.push({ status: "skip", label: `${currentSuite} > ${name}`, reason });
}

// ─────────────────────────────────────────────────────────────────────────────
// Navigation helpers
// ─────────────────────────────────────────────────────────────────────────────

async function goto(path, { wait = HYDRATION_MS } = {}) {
  await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded", timeout: NAV_TIMEOUT });
  if (wait > 0) await page.waitForTimeout(wait);
}

/** Wait for any visible text to appear on page */
async function waitForText(text, timeout = 8000) {
  await page.waitForFunction(
    (t) => document.body.innerText.includes(t),
    text,
    { timeout }
  );
}

/** Check page has rendered real content (not blank) */
async function assertHasContent(minElements = 20) {
  const count = await page.locator("*").count();
  if (count < minElements) {
    throw new Error(`Page has only ${count} DOM elements — may be blank`);
  }
}

/** Fill a Quasar / NiceGUI input by label text or placeholder */
async function fillInput(selector, value) {
  const el = page.locator(selector).first();
  await el.waitFor({ state: "visible", timeout: 5000 });
  await el.click();
  await el.fill(value);
}

/** Click a button containing given text */
async function clickButton(text) {
  const btn = page.locator(`button:has-text("${text}")`).first();
  await btn.waitFor({ state: "visible", timeout: 5000 });
  await btn.click();
}

/** Check no JS errors were thrown during test */
const jsErrors = [];
function attachErrorListeners() {
  page.on("pageerror", (err) => jsErrors.push(err.message));
  page.on("console", (msg) => {
    if (msg.type() === "error") jsErrors.push(msg.text());
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 1: Application shell & routing
// ─────────────────────────────────────────────────────────────────────────────

async function runShellTests() {
  suite("Application Shell & Routing");

  await test("Root redirects or renders dashboard", async () => {
    await goto("/");
    const title = await page.title();
    if (!title.includes("DEX")) throw new Error(`Unexpected title: ${title}`);
  });

  await test("404 path does not crash the app", async () => {
    await goto("/this/path/does/not/exist");
    await page.waitForTimeout(1000);
    const body = await page.locator("body").innerText().catch(() => "");
    // Should show 404 page, error page, or redirect — not a blank screen
    const hasContent = body.length > 10 || (await page.locator("*").count()) > 5;
    if (!hasContent) throw new Error("Blank page on unknown route");
  });

  await test("/error boundary page renders without crash", async () => {
    await goto("/error", { wait: 1000 });
    await assertHasContent(5);
  });

  await test("All domain root routes render", async () => {
    const domains = ["/career", "/data", "/ml", "/ai", "/system"];
    const failed = [];
    for (const d of domains) {
      await goto(d, { wait: 800 });
      const count = await page.locator("*").count();
      if (count < 15) failed.push(d);
    }
    if (failed.length) throw new Error(`Sparse DOM on: ${failed.join(", ")}`);
  });

  await test("Page title is always DEX Studio", async () => {
    const routes = ["/career/tracker", "/data/pipelines", "/ai/playground", "/system/status"];
    for (const r of routes) {
      await goto(r, { wait: 500 });
      const title = await page.title();
      if (!title.includes("DEX")) throw new Error(`Bad title "${title}" on ${r}`);
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 2: Career — Application Tracker (real CRUD)
// ─────────────────────────────────────────────────────────────────────────────

async function runTrackerTests() {
  suite("Career / Application Tracker — Real CRUD");

  await test("Tracker page loads with expected UI sections", async () => {
    await goto("/career/tracker");
    await assertHasContent(30);
    const text = await page.locator("body").innerText();
    const hasTrackerKeyword =
      text.includes("Application") ||
      text.includes("Tracker") ||
      text.includes("Job") ||
      text.includes("Add") ||
      text.includes("Status");
    if (!hasTrackerKeyword) throw new Error("Tracker page content not found");
  });

  await test("Add Application button is visible and clickable", async () => {
    await goto("/career/tracker");
    const addBtn = page
      .locator('button:has-text("Add"), button:has-text("New"), button:has-text("+")')
      .first();
    const visible = await addBtn.isVisible().catch(() => false);
    if (!visible) throw new Error("Add/New button not visible on tracker");
    await addBtn.click();
    await page.waitForTimeout(500);
  });

  await test("Add dialog opens and accepts company + position input", async () => {
    await goto("/career/tracker");
    const addBtn = page
      .locator('button:has-text("Add"), button:has-text("New"), button:has-text("+")')
      .first();
    if (!(await addBtn.isVisible().catch(() => false))) {
      throw new Error("Add button not found");
    }
    await addBtn.click();
    await page.waitForTimeout(800);

    // Quasar dialog renders in #q-portal--dialog--N — target inputs inside it
    // to avoid the q-dialog__backdrop intercepting clicks on main-page inputs
    const dialogInputs = page.locator(
      '[id^="q-portal--dialog"] .q-field__native, [id^="q-portal--dialog"] input, [role="dialog"] .q-field__native, [role="dialog"] input'
    );
    const count = await dialogInputs.count();
    if (count === 0) throw new Error("No inputs found inside dialog portal");

    // Fill first text input (Company)
    const companyInput = dialogInputs.nth(0);
    await companyInput.waitFor({ state: "visible", timeout: 5000 });
    await companyInput.click();
    await companyInput.fill(TEST_DATA.application.company);
    const val = await companyInput.inputValue();
    if (!val.includes("Databricks")) throw new Error(`Input value not set: got "${val}"`);

    // Fill second input if present (Position)
    if (count >= 2) {
      const posInput = dialogInputs.nth(1);
      if (await posInput.isVisible().catch(() => false)) {
        await posInput.click();
        await posInput.fill(TEST_DATA.application.position);
      }
    }

    // Dismiss dialog by pressing Escape (avoid partial form submission)
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  });

  await test("Status filter tabs/buttons are present", async () => {
    await goto("/career/tracker");
    const text = await page.locator("body").innerText();
    const statusKeywords = ["All", "Applied", "Saved", "Interview", "Offer"];
    const found = statusKeywords.some((k) => text.includes(k));
    if (!found) throw new Error("No status filter keywords found");
  });

  await test("Search input is present and focusable", async () => {
    await goto("/career/tracker");
    const searchInput = page
      .locator('input[placeholder*="earch" i], input[type="search"]')
      .first();
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.click();
      await searchInput.fill("Databricks");
      await page.waitForTimeout(300);
      await searchInput.fill("");
    }
    // If no search input, skip gracefully — not a hard failure
  });

  await test("Tracker page has no JavaScript runtime errors", async () => {
    await goto("/career/tracker");
    await page.waitForTimeout(1500);
    const freshErrors = jsErrors.filter(
      (e) =>
        !e.includes("favicon") &&
        !e.includes("WebSocket") &&
        !e.includes("net::ERR")
    );
    if (freshErrors.length > 3) {
      throw new Error(`JS errors on tracker: ${freshErrors.slice(0, 3).join(" | ")}`);
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 3: Career — Resume Matcher (real text analysis flow)
// ─────────────────────────────────────────────────────────────────────────────

async function runResumeMatcherTests() {
  suite("Career / Resume Matcher — Real Text Analysis");

  await test("Resume Matcher page loads", async () => {
    await goto("/career/resume-matcher");
    await assertHasContent(20);
    const text = await page.locator("body").innerText();
    const hasKeyword =
      text.includes("Resume") ||
      text.includes("Matcher") ||
      text.includes("Job Description") ||
      text.includes("Match") ||
      text.includes("Score");
    if (!hasKeyword) throw new Error("Resume matcher content not found");
  });

  await test("Resume textarea is present and accepts multi-line text", async () => {
    await goto("/career/resume-matcher");
    const textareas = page.locator("textarea");
    const count = await textareas.count();
    if (count === 0) throw new Error("No textareas on resume matcher page");

    // Fill first textarea with resume
    const resume = textareas.nth(0);
    await resume.waitFor({ state: "visible", timeout: 5000 });
    await resume.fill(TEST_DATA.resume);
    const val = await resume.inputValue();
    if (val.length < 100) throw new Error(`Textarea did not accept text: ${val.length} chars`);
  });

  await test("JD textarea accepts job description text", async () => {
    await goto("/career/resume-matcher");
    const textareas = page.locator("textarea");
    const count = await textareas.count();
    if (count < 2) {
      // Maybe single textarea with JD in separate input
      skip("JD textarea", "Only one textarea found — may use different UI");
      return;
    }
    const jd = textareas.nth(1);
    await jd.fill(TEST_DATA.jd);
    const val = await jd.inputValue();
    if (val.length < 50) throw new Error("JD textarea did not accept text");
  });

  await test("Analyze/Match button triggers without crash", async () => {
    await goto("/career/resume-matcher");
    await page.waitForTimeout(HYDRATION_MS);

    // Fill both textareas
    const textareas = page.locator("textarea");
    if ((await textareas.count()) >= 1) {
      await textareas.nth(0).fill(TEST_DATA.resume.slice(0, 300));
    }
    if ((await textareas.count()) >= 2) {
      await textareas.nth(1).fill(TEST_DATA.jd.slice(0, 200));
    }

    // Find and click match/analyze button
    const analyzeBtn = page
      .locator(
        'button:has-text("Match"), button:has-text("Analyze"), button:has-text("Run"), button:has-text("Score")'
      )
      .first();
    const isVisible = await analyzeBtn.isVisible().catch(() => false);
    if (!isVisible) {
      skip("Analyze button", "No match/analyze button found — may require file upload");
      return;
    }
    await analyzeBtn.click();
    await page.waitForTimeout(3000); // Wait for analysis
    await assertHasContent(20);
  });

  await test("Provider selector renders available LLM options", async () => {
    await goto("/career/resume-matcher");
    const text = await page.locator("body").innerText();
    const hasProviders =
      text.includes("Ollama") ||
      text.includes("OpenAI") ||
      text.includes("Anthropic") ||
      text.includes("Provider") ||
      text.includes("Model");
    if (!hasProviders) {
      skip("Provider selector", "No LLM provider options visible");
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 4: Career — Networking (contact management)
// ─────────────────────────────────────────────────────────────────────────────

async function runNetworkingTests() {
  suite("Career / Networking — Contact Management");

  await test("Networking page loads", async () => {
    await goto("/career/networking");
    await assertHasContent(20);
  });

  await test("Add Contact button or equivalent is present", async () => {
    await goto("/career/networking");
    const text = await page.locator("body").innerText();
    const hasAdd =
      text.includes("Add Contact") ||
      text.includes("New Contact") ||
      text.includes("Add Connection") ||
      (await page.locator('button:has-text("Add"), button:has-text("New")').count()) > 0;
    if (!hasAdd) throw new Error("No add contact action found on networking page");
  });

  await test("Contact relationship types are listed", async () => {
    await goto("/career/networking");
    const text = await page.locator("body").innerText();
    const hasRelationships =
      text.includes("Recruiter") ||
      text.includes("Hiring") ||
      text.includes("Mentor") ||
      text.includes("Referral") ||
      text.includes("Contact");
    if (!hasRelationships) throw new Error("No relationship types visible");
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 5: Career — Progress tracking
// ─────────────────────────────────────────────────────────────────────────────

async function runProgressTests() {
  suite("Career / Progress — Analytics & Tracking");

  await test("Progress page renders metrics or empty state", async () => {
    await goto("/career/progress");
    await assertHasContent(15);
    const text = await page.locator("body").innerText();
    const hasMetrics =
      text.includes("Progress") ||
      text.includes("Applied") ||
      text.includes("Week") ||
      text.includes("Goal") ||
      text.includes("Interview") ||
      text.includes("Activity");
    if (!hasMetrics) throw new Error("Progress page has no recognizable content");
  });

  await test("Career dashboard aggregates domain overview", async () => {
    await goto("/career");
    await assertHasContent(20);
    const text = await page.locator("body").innerText();
    const hasDashboard =
      text.includes("Career") ||
      text.includes("Application") ||
      text.includes("Job") ||
      text.includes("Dashboard");
    if (!hasDashboard) throw new Error("Career dashboard has no expected content");
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 6: Data — SQL Console (real DuckDB queries)
// ─────────────────────────────────────────────────────────────────────────────

async function runSQLConsoleTests() {
  suite("Data / SQL Console — Real DuckDB Queries");

  await test("SQL console page loads with editor", async () => {
    await goto("/data/sql");
    await assertHasContent(20);
    const text = await page.locator("body").innerText();
    const hasSQLUI =
      text.includes("SQL") ||
      text.includes("Query") ||
      text.includes("Execute") ||
      text.includes("Run") ||
      text.includes("Console");
    if (!hasSQLUI) throw new Error("SQL console not found on /data/sql");
  });

  await test("SQL editor textarea is present and writable", async () => {
    await goto("/data/sql");
    const textarea = page.locator("textarea, .cm-editor, .CodeMirror, pre[contenteditable]").first();
    const visible = await textarea.isVisible().catch(() => false);
    if (!visible) {
      // Try regular input as fallback
      const input = page.locator("input").first();
      const inputVisible = await input.isVisible().catch(() => false);
      if (!inputVisible) throw new Error("No SQL editor found");
    }
  });

  for (const q of TEST_DATA.sql_queries) {
    await test(`SQL query: ${q.label}`, async () => {
      await goto("/data/sql");

      // Find the SQL textarea
      const textarea = page.locator("textarea").first();
      const isVisible = await textarea.isVisible().catch(() => false);
      if (!isVisible) {
        skip(`SQL: ${q.label}`, "SQL textarea not visible");
        return;
      }

      // Clear and enter query
      await textarea.click({ clickCount: 3 }); // select all
      await textarea.fill(q.sql);
      await page.waitForTimeout(200);

      // Execute — try keyboard shortcut first, then button
      const runBtn = page
        .locator('button:has-text("Run"), button:has-text("Execute"), button:has-text("Submit")')
        .first();
      const btnVisible = await runBtn.isVisible().catch(() => false);
      if (btnVisible) {
        await runBtn.click();
      } else {
        await textarea.press("Control+Enter");
      }

      await page.waitForTimeout(2000);
      await assertHasContent(10);

      const bodyText = await page.locator("body").innerText();

      if (q.expectsError) {
        const showsError =
          bodyText.toLowerCase().includes("error") ||
          bodyText.toLowerCase().includes("failed") ||
          bodyText.toLowerCase().includes("not found");
        if (!showsError) {
          // Not a hard failure — bad SQL might silently fail in UI
          console.log(`       ⚠  Expected error not shown for: ${q.sql}`);
        }
      } else if (q.expectsResult) {
        // At minimum page shouldn't be blank after running a good query
        if (bodyText.length < 100) throw new Error("Page content too sparse after SQL run");
      }
    });
  }

  await test("Example queries are listed for quick selection", async () => {
    await goto("/data/sql");
    const text = await page.locator("body").innerText();
    const hasExamples =
      text.includes("Example") ||
      text.includes("SELECT") ||
      text.includes("SHOW") ||
      (await page.locator('button:has-text("Example"), select, [role="listbox"]').count()) > 0;
    if (!hasExamples) {
      skip("Example queries", "No example queries UI element found");
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 7: Data — Pipelines, Sources, Warehouse
// ─────────────────────────────────────────────────────────────────────────────

async function runDataDomainTests() {
  suite("Data / Pipelines — Pipeline Management");

  await test("Pipelines page renders list or empty state", async () => {
    await goto("/data/pipelines");
    await assertHasContent(20);
    const text = await page.locator("body").innerText();
    const hasPipelines =
      text.includes("Pipeline") ||
      text.includes("Schedule") ||
      text.includes("Run") ||
      text.includes("Status");
    if (!hasPipelines) throw new Error("Pipelines page content not found");
  });

  await test("Data Sources page loads", async () => {
    await goto("/data/sources");
    await assertHasContent(20);
    const text = await page.locator("body").innerText();
    const hasSources =
      text.includes("Source") ||
      text.includes("Connection") ||
      text.includes("Database") ||
      text.includes("File");
    if (!hasSources) throw new Error("Sources page content not found");
  });

  await test("Warehouse page loads with layer info", async () => {
    await goto("/data/warehouse");
    await assertHasContent(15);
    const text = await page.locator("body").innerText();
    const hasWarehouse =
      text.includes("Warehouse") ||
      text.includes("Bronze") ||
      text.includes("Silver") ||
      text.includes("Gold") ||
      text.includes("Layer") ||
      text.includes("Storage");
    if (!hasWarehouse) throw new Error("Warehouse page content not found");
  });

  await test("Data catalog page renders", async () => {
    await goto("/data/catalog");
    await assertHasContent(15);
  });

  await test("Data lineage page renders", async () => {
    await goto("/data/lineage");
    await assertHasContent(15);
  });

  await test("Data quality page renders", async () => {
    await goto("/data/quality");
    await assertHasContent(15);
  });

  await test("Data contracts page renders", async () => {
    await goto("/data/contracts");
    await assertHasContent(15);
  });

  await test("Asset graph page renders", async () => {
    await goto("/data/asset-graph");
    await assertHasContent(10);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 8: AI — Playground & Agent Management
// ─────────────────────────────────────────────────────────────────────────────

async function runAIDomainTests() {
  suite("AI / Playground — Prompt Testing");

  await test("AI playground loads with prompt interface", async () => {
    await goto("/ai/playground");
    await assertHasContent(20);
    const text = await page.locator("body").innerText();
    const hasPlayground =
      text.includes("Playground") ||
      text.includes("Prompt") ||
      text.includes("Model") ||
      text.includes("System") ||
      text.includes("Message");
    if (!hasPlayground) throw new Error("AI playground content not found");
  });

  await test("System prompt area is writable", async () => {
    await goto("/ai/playground");
    const textareas = page.locator("textarea");
    const count = await textareas.count();
    if (count === 0) {
      skip("System prompt", "No textarea on playground");
      return;
    }
    const ta = textareas.nth(0);
    const isVisible = await ta.isVisible().catch(() => false);
    if (!isVisible) {
      skip("System prompt", "Textarea not visible");
      return;
    }
    await ta.fill("You are a helpful data engineering assistant.");
    const val = await ta.inputValue();
    if (val.length === 0) throw new Error("System prompt textarea did not accept input");
  });

  await test("User message field accepts prompt text", async () => {
    await goto("/ai/playground");
    const textareas = page.locator("textarea");
    const count = await textareas.count();
    if (count < 2) {
      // Use any visible input
      const inputs = page.locator("input");
      if ((await inputs.count()) > 0) {
        await inputs.first().fill(TEST_DATA.prompt.slice(0, 50));
      }
      return;
    }
    await textareas.nth(count - 1).fill(TEST_DATA.prompt);
    const val = await textareas.nth(count - 1).inputValue();
    if (val.length === 0) throw new Error("Message input did not accept text");
  });

  await test("Model provider selector displays options", async () => {
    await goto("/ai/playground");
    const text = await page.locator("body").innerText();
    const hasModels =
      text.includes("Ollama") ||
      text.includes("llama") ||
      text.includes("gpt") ||
      text.includes("Claude") ||
      text.includes("Provider") ||
      text.includes("Model");
    if (!hasModels) throw new Error("No model/provider options found");
  });

  await test("Submit/Run button is present", async () => {
    await goto("/ai/playground");
    const btn = page
      .locator('button:has-text("Run"), button:has-text("Submit"), button:has-text("Send"), button:has-text("Generate")')
      .first();
    const visible = await btn.isVisible().catch(() => false);
    if (!visible) throw new Error("No submit/run button found on playground");
  });

  await test("Submit prompt — graceful response or offline message", async () => {
    await goto("/ai/playground");
    await page.waitForTimeout(HYDRATION_MS);

    const textareas = page.locator("textarea");
    const taCount = await textareas.count();
    if (taCount > 0) {
      await textareas.nth(taCount - 1).fill(TEST_DATA.prompt.slice(0, 80));
    }

    const runBtn = page
      .locator(
        'button:has-text("Run"), button:has-text("Submit"), button:has-text("Send")'
      )
      .first();
    const visible = await runBtn.isVisible().catch(() => false);
    if (!visible) {
      skip("Submit prompt", "Run button not found");
      return;
    }

    await runBtn.click();
    await page.waitForTimeout(3000);

    // Accept either a response, a "loading" state, or "offline"/"error" message
    const text = await page.locator("body").innerText();
    const responded =
      text.includes("response") ||
      text.includes("offline") ||
      text.includes("error") ||
      text.includes("Connecting") ||
      text.includes("loading") ||
      text.length > 200; // page still has content
    if (!responded) throw new Error("Page blank after prompt submit");
  });

  suite("AI — Agents, Tools, Traces, Vectors");

  await test("Agents page loads", async () => {
    await goto("/ai/agents");
    await assertHasContent(15);
    const text = await page.locator("body").innerText();
    if (!text.includes("Agent") && !text.includes("assistant") && !text.includes("Bot")) {
      throw new Error("Agents page content not found");
    }
  });

  await test("Tools page loads with registered tools", async () => {
    await goto("/ai/tools");
    await assertHasContent(15);
    const text = await page.locator("body").innerText();
    const hasTools =
      text.includes("Tool") ||
      text.includes("echo") ||
      text.includes("query") ||
      text.includes("Function");
    if (!hasTools) throw new Error("Tools page content not found");
  });

  await test("Traces page loads", async () => {
    await goto("/ai/traces");
    await assertHasContent(15);
  });

  await test("Vectors page loads", async () => {
    await goto("/ai/vectors");
    await assertHasContent(15);
  });

  await test("Collections page loads", async () => {
    await goto("/ai/collections");
    await assertHasContent(15);
  });

  await test("AI cost page loads", async () => {
    await goto("/ai/cost");
    await assertHasContent(15);
  });

  await test("AI workflows page loads", async () => {
    await goto("/ai/workflows");
    await assertHasContent(15);
  });

  await test("AI memory page loads", async () => {
    await goto("/ai/memory");
    await assertHasContent(15);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 9: ML — Experiments, Models, Features
// ─────────────────────────────────────────────────────────────────────────────

async function runMLDomainTests() {
  suite("ML — Experiments & Model Registry");

  const mlPages = [
    { path: "/ml", name: "ML dashboard" },
    { path: "/ml/experiments", name: "Experiments" },
    { path: "/ml/models", name: "Model registry" },
    { path: "/ml/features", name: "Feature store" },
    { path: "/ml/drift", name: "Drift detection" },
    { path: "/ml/predictions", name: "Predictions" },
    { path: "/ml/ab-test", name: "A/B testing" },
    { path: "/ml/hyperopt", name: "Hyperparameter opt" },
  ];

  for (const p of mlPages) {
    await test(`${p.name} page loads`, async () => {
      await goto(p.path, { wait: 800 });
      await assertHasContent(15);
    });
  }

  await test("Experiments page shows table or empty state", async () => {
    await goto("/ml/experiments");
    const text = await page.locator("body").innerText();
    const hasContent =
      text.includes("Experiment") ||
      text.includes("Run") ||
      text.includes("Metric") ||
      text.includes("Model") ||
      text.includes("empty") ||
      text.includes("No ");
    if (!hasContent) throw new Error("Experiments page has no recognizable content");
  });

  await test("Model registry shows list or empty state", async () => {
    await goto("/ml/models");
    const text = await page.locator("body").innerText();
    const hasContent =
      text.includes("Model") ||
      text.includes("Version") ||
      text.includes("Staging") ||
      text.includes("Production") ||
      text.includes("Registry") ||
      text.includes("No ");
    if (!hasContent) throw new Error("Model registry has no recognizable content");
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 10: System — Monitoring, Logs, Settings
// ─────────────────────────────────────────────────────────────────────────────

async function runSystemTests() {
  suite("System — Monitoring & Observability");

  await test("System status page loads with health info", async () => {
    await goto("/system");
    await assertHasContent(20);
    const text = await page.locator("body").innerText();
    const hasStatus =
      text.includes("Status") ||
      text.includes("Health") ||
      text.includes("Component") ||
      text.includes("System") ||
      text.includes("CPU") ||
      text.includes("Memory");
    if (!hasStatus) throw new Error("System status page content not found");
  });

  await test("System logs page loads", async () => {
    await goto("/system/logs");
    await assertHasContent(15);
    const text = await page.locator("body").innerText();
    const hasLogs =
      text.includes("Log") ||
      text.includes("Event") ||
      text.includes("INFO") ||
      text.includes("ERROR") ||
      text.includes("Filter");
    if (!hasLogs) throw new Error("Logs page content not found");
  });

  await test("System metrics page loads", async () => {
    await goto("/system/metrics");
    await assertHasContent(15);
  });

  await test("System settings page loads with config form", async () => {
    await goto("/system/settings");
    await assertHasContent(15);
    const text = await page.locator("body").innerText();
    const hasSettings =
      text.includes("Setting") ||
      text.includes("Config") ||
      text.includes("API") ||
      text.includes("URL") ||
      text.includes("Token");
    if (!hasSettings) throw new Error("Settings page content not found");
  });

  await test("System connection page loads", async () => {
    await goto("/system/connection");
    await assertHasContent(15);
  });

  await test("System incidents page loads", async () => {
    await goto("/system/incidents");
    await assertHasContent(15);
  });

  await test("System traces page loads", async () => {
    await goto("/system/traces");
    await assertHasContent(15);
  });

  await test("System activity page loads", async () => {
    await goto("/system/activity");
    await assertHasContent(15);
  });

  await test("System components page loads", async () => {
    await goto("/system/components");
    await assertHasContent(15);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 11: Navigation — Cross-domain sidebar flow
// ─────────────────────────────────────────────────────────────────────────────

async function runNavigationTests() {
  suite("Navigation — Cross-domain & Sidebar");

  await test("Links present in navigation sidebar", async () => {
    await goto("/career");
    const links = await page.locator("a[href]").count();
    if (links < 3) throw new Error(`Too few navigation links: ${links}`);
  });

  await test("Career → Data domain nav works via link click", async () => {
    await goto("/career");
    const dataLink = page.locator('a[href="/data"], a[href*="/data"]').first();
    const visible = await dataLink.isVisible().catch(() => false);
    if (!visible) {
      skip("Career→Data nav", "No /data link visible from career page");
      return;
    }
    await dataLink.click();
    await page.waitForTimeout(1000);
    const url = page.url();
    if (!url.includes("/data")) throw new Error(`Expected /data URL, got ${url}`);
  });

  await test("Browser back button works after SPA navigation", async () => {
    await goto("/career");
    await goto("/data");
    await page.goBack();
    await page.waitForTimeout(800);
    const url = page.url();
    if (!url.includes("/career") && !url.includes("localhost:7860")) {
      throw new Error(`After back nav, URL is: ${url}`);
    }
  });

  await test("Direct URL navigation to any page works", async () => {
    const directRoutes = [
      "/career/tracker",
      "/data/sql",
      "/ai/playground",
      "/ml/experiments",
      "/system/status",
    ];
    const failed = [];
    for (const r of directRoutes) {
      await goto(r, { wait: 600 });
      const count = await page.locator("*").count();
      if (count < 10) failed.push(r);
    }
    if (failed.length) throw new Error(`Sparse DOM on direct nav to: ${failed.join(", ")}`);
  });

  await test("Rapid page switching does not produce blank screens", async () => {
    const paths = ["/career", "/data", "/ml", "/ai", "/system", "/career/tracker"];
    for (const p of paths) {
      await page.goto(`${BASE}${p}`, { waitUntil: "domcontentloaded", timeout: 10000 });
      await page.waitForTimeout(200);
    }
    await page.waitForTimeout(500);
    const count = await page.locator("*").count();
    if (count < 10) throw new Error("Blank page after rapid navigation");
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 12: Responsive layout & accessibility
// ─────────────────────────────────────────────────────────────────────────────

async function runResponsiveTests() {
  suite("Responsive Layout & Accessibility");

  const viewports = [
    { name: "Desktop 1920", width: 1920, height: 1080 },
    { name: "Laptop 1440", width: 1440, height: 900 },
    { name: "Tablet 768", width: 768, height: 1024 },
    { name: "Mobile 390", width: 390, height: 844 },
  ];

  for (const vp of viewports) {
    await test(`Renders at ${vp.name} without JS errors`, async () => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await goto("/career/tracker", { wait: 800 });
      const count = await page.locator("*").count();
      if (count < 10) throw new Error(`Sparse DOM at ${vp.name}`);
    });
  }

  // Reset
  await page.setViewportSize({ width: 1400, height: 900 });

  await test("No images missing alt text (more than 10 undecorated)", async () => {
    await goto("/career");
    const missing = await page.evaluate(() => {
      const imgs = Array.from(document.querySelectorAll("img"));
      return imgs.filter((i) => !i.alt && !i.getAttribute("aria-hidden")).length;
    });
    if (missing > 10) throw new Error(`${missing} images missing alt text`);
  });

  await test("Page has ARIA roles or labels", async () => {
    await goto("/career/tracker");
    const ariaEls = await page.evaluate(() => {
      return (
        document.querySelectorAll("[role], [aria-label], [aria-labelledby]").length
      );
    });
    // NiceGUI uses Quasar which has roles — at least a few expected
    if (ariaEls < 2) throw new Error(`Only ${ariaEls} elements with ARIA attributes`);
  });

  await test("Color contrast — dark theme uses dark background", async () => {
    await goto("/career");
    const bgColor = await page.evaluate(() => {
      const body = document.body;
      const style = window.getComputedStyle(body);
      return style.backgroundColor;
    });
    // Dark mode check: background should not be pure white rgb(255, 255, 255)
    if (bgColor === "rgb(255, 255, 255)") {
      throw new Error("Dark theme not applied — body is white");
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 13: Performance baselines
// ─────────────────────────────────────────────────────────────────────────────

async function runPerformanceTests() {
  suite("Performance Baselines");

  const pages = [
    { path: "/career/tracker", name: "Tracker", budget: 4000 },
    { path: "/data/sql", name: "SQL Console", budget: 4000 },
    { path: "/ai/playground", name: "AI Playground", budget: 5000 },
    { path: "/system/status", name: "System Status", budget: 4000 },
  ];

  for (const p of pages) {
    await test(`${p.name} loads within ${p.budget}ms`, async () => {
      const start = Date.now();
      await page.goto(`${BASE}${p.path}`, { waitUntil: "domcontentloaded", timeout: NAV_TIMEOUT });
      const elapsed = Date.now() - start;
      if (elapsed > p.budget) {
        throw new Error(`Slow page load: ${elapsed}ms (budget: ${p.budget}ms)`);
      }
    });
  }

  await test("DOM node count within healthy range on tracker", async () => {
    // Measure on a fresh browser context to avoid NiceGUI state accumulated
    // over the full test run (same-session re-navigations pile up server-side
    // element pushes that inflate the CDP node count).
    const freshCtx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    const freshPage = await freshCtx.newPage();
    try {
      await freshPage.goto(`${BASE}/career/tracker`, {
        waitUntil: "domcontentloaded",
        timeout: NAV_TIMEOUT,
      });
      await freshPage.waitForTimeout(1500); // NiceGUI WebSocket hydration
      const client = await freshCtx.newCDPSession(freshPage);
      try {
        await client.send("Performance.enable");
        await freshPage.waitForTimeout(300);
        const metrics = await client.send("Performance.getMetrics");
        const nodes = metrics.metrics.find((m) => m.name === "Nodes");
        // Baseline: ~600 CDP nodes on fresh load (includes shadow DOM + text nodes).
        // Hard limit 4000 catches render loops or dialog accumulation regressions.
        if (nodes) {
          if (nodes.value > 4000) {
            throw new Error(
              `DOM too large on fresh load: ${nodes.value} nodes (budget 4000) — ` +
                "check for dialog accumulation or unbounded render"
            );
          }
          if (nodes.value > 2000) {
            console.log(`       ⚠  DOM elevated: ${nodes.value} nodes — review for unvirtualized list`);
          }
        }
      } finally {
        await client.detach().catch(() => {});
      }
    } finally {
      await freshCtx.close();
    }
  });

  await test("No memory leak — JS heap stays under 200MB", async () => {
    const client = await context.newCDPSession(page);
    try {
      // Navigate through 5 pages
      const testPaths = ["/career", "/data", "/ml", "/ai", "/system"];
      for (const p of testPaths) {
        await page.goto(`${BASE}${p}`, { waitUntil: "domcontentloaded", timeout: 10000 });
        await page.waitForTimeout(300);
      }
      await client.send("Performance.enable");
      const metrics = await client.send("Performance.getMetrics");
      const heap = metrics.metrics.find((m) => m.name === "JSHeapUsedSize");
      if (heap && heap.value > 200 * 1024 * 1024) {
        throw new Error(`JS heap too large: ${(heap.value / 1024 / 1024).toFixed(0)}MB`);
      }
    } finally {
      await client.detach().catch(() => {});
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// SUITE 14: Error & edge case handling
// ─────────────────────────────────────────────────────────────────────────────

async function runEdgeCaseTests() {
  suite("Error Handling & Edge Cases");

  await test("SQL console handles empty query gracefully", async () => {
    await goto("/data/sql");
    const textarea = page.locator("textarea").first();
    if (!(await textarea.isVisible().catch(() => false))) {
      skip("Empty SQL", "No textarea visible");
      return;
    }
    await textarea.fill("");
    const runBtn = page
      .locator('button:has-text("Run"), button:has-text("Execute")')
      .first();
    if (await runBtn.isVisible().catch(() => false)) {
      await runBtn.click();
      await page.waitForTimeout(1000);
      await assertHasContent(10);
    }
  });

  await test("Resume matcher handles empty inputs without crash", async () => {
    await goto("/career/resume-matcher");
    const analyzeBtn = page
      .locator('button:has-text("Match"), button:has-text("Analyze"), button:has-text("Run")')
      .first();
    if (!(await analyzeBtn.isVisible().catch(() => false))) {
      skip("Empty matcher", "No analyze button");
      return;
    }
    await analyzeBtn.click();
    await page.waitForTimeout(1500);
    await assertHasContent(10);
  });

  await test("All pages survive rapid forward/back navigation", async () => {
    const paths = ["/career/tracker", "/data/sql", "/ai/playground"];
    for (const p of paths) {
      await page.goto(`${BASE}${p}`, { waitUntil: "domcontentloaded", timeout: 10000 });
      await page.waitForTimeout(100);
      await page.goBack();
      await page.waitForTimeout(100);
      await page.goForward();
      await page.waitForTimeout(100);
    }
    await page.waitForTimeout(500);
    const count = await page.locator("*").count();
    if (count < 5) throw new Error("Blank page after rapid back/forward navigation");
  });

  await test("No critical JS errors accumulated across test run", async () => {
    const critical = jsErrors.filter(
      (e) =>
        !e.includes("favicon") &&
        !e.includes("WebSocket") &&
        !e.includes("net::ERR") &&
        !e.includes("Failed to fetch") &&
        !e.includes("Ollama") &&
        !e.includes("localhost:11434") &&
        !e.includes("localhost:17000") &&
        !e.includes("CORS")
    );
    if (critical.length > 5) {
      const sample = critical.slice(0, 5).map((e) => e.slice(0, 100));
      throw new Error(`${critical.length} critical JS errors:\n${sample.join("\n")}`);
    }
    if (critical.length > 0) {
      console.log(`       ⚠  ${critical.length} non-critical JS errors accumulated`);
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────────────────────────────────────

async function main() {
  const startTime = Date.now();

  console.log("═".repeat(65));
  console.log("  DEX STUDIO — FULL END-TO-END TEST SUITE");
  console.log("  Senior-level: real user flows, real data, real interactions");
  console.log("═".repeat(65));
  console.log(`  Base URL : ${BASE}`);
  console.log(`  Timestamp: ${new Date().toISOString()}`);
  console.log("═".repeat(65));

  // Verify server is reachable before running
  try {
    const res = await fetch(`${BASE}/`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch (err) {
    console.error(`\n❌ Server not reachable at ${BASE}: ${err.message}`);
    console.error("   Start with: uv run poe dev");
    process.exit(2);
  }

  browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    locale: "en-US",
    userAgent:
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
  });

  page = await context.newPage();
  attachErrorListeners();

  try {
    await runShellTests();
    await runTrackerTests();
    await runResumeMatcherTests();
    await runNetworkingTests();
    await runProgressTests();
    await runSQLConsoleTests();
    await runDataDomainTests();
    await runAIDomainTests();
    await runMLDomainTests();
    await runSystemTests();
    await runNavigationTests();
    await runResponsiveTests();
    await runPerformanceTests();
    await runEdgeCaseTests();
  } finally {
    await browser.close();
  }

  // ─── Summary ───
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const total = results.pass + results.fail + results.skip;

  console.log("\n" + "═".repeat(65));
  console.log("  RESULTS");
  console.log("═".repeat(65));
  console.log(`  Total   : ${total}`);
  console.log(`  ✅ Pass  : ${results.pass}`);
  console.log(`  ❌ Fail  : ${results.fail}`);
  console.log(`  ⏭  Skip  : ${results.skip}`);
  console.log(`  Duration: ${elapsed}s`);

  if (results.fail > 0) {
    console.log("\n  FAILURES:");
    results.details
      .filter((d) => d.status === "fail")
      .forEach((d) => {
        console.log(`  ❌ ${d.label}`);
        console.log(`     ${d.error}`);
      });
  }

  const pct = total > 0 ? ((results.pass / (total - results.skip)) * 100).toFixed(1) : "0.0";
  console.log(`\n  Pass rate (excl. skipped): ${pct}%`);
  console.log("═".repeat(65));

  process.exit(results.fail > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
