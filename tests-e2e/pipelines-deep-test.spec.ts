import { test, expect } from "@playwright/test";

test.describe("pipelines page — autonomous deep test", () => {
  test("explore every interactive element, validate structure and behavior", async ({ page }) => {
    test.setTimeout(60_000);

    const consoleErrors: string[] = [];
    const networkErrors: { url: string; status: number }[] = [];

    page.on("response", (r) => {
      if (r.status() >= 400) networkErrors.push({ url: r.url(), status: r.status() });
    });
    page.on("console", (m) => {
      if (m.type() === "error") consoleErrors.push(m.text());
    });

    await page.goto("/data/pipelines", { waitUntil: "load" });
    await expect(page).toHaveTitle(/Pipelines/);

    // ── 1. Autonomous element discovery ──
    const discovered = await page.evaluate(() => {
      const inventory: Record<string, any> = {};

      inventory.title = document.title;
      inventory.forms = Array.from(document.forms).map((f) => ({
        action: f.action,
        method: f.method,
        fields: Array.from(f.elements).map((e: any) => ({ name: e.name, type: e.type, placeholder: e.placeholder })),
      }));

      inventory.buttons = Array.from(document.querySelectorAll("button")).map((b) => ({
        text: (b.textContent || "").trim().slice(0, 40),
        type: b.type,
        visible: b.offsetParent !== null,
        hxGet: b.getAttribute("hx-get"),
        hxPost: b.getAttribute("hx-post"),
        onclick: !!b.getAttribute("onclick"),
        dataTip: b.getAttribute("data-tip"),
      }));

      inventory.selects = Array.from(document.querySelectorAll("select")).map((s) => ({
        name: s.name,
        options: Array.from(s.options).map((o: any) => o.text.trim()),
      }));

      inventory.textareas = Array.from(document.querySelectorAll("textarea")).map((t) => ({
        name: t.name,
        rows: t.rows,
        placeholder: t.placeholder,
      }));

      inventory.pipelines = Array.from(document.querySelectorAll("[data-name]")).map((el) => ({
        name: el.getAttribute("data-name"),
        status: el.getAttribute("data-status"),
        schedule: el.getAttribute("data-schedule"),
        lastRun: el.getAttribute("data-last-run"),
        duration: el.getAttribute("data-duration"),
        rowsIn: el.getAttribute("data-rows-in"),
        rowsOut: el.getAttribute("data-rows-out"),
      }));

      inventory.csrfTokens = Array.from(document.querySelectorAll('input[name="_csrf"]')).length;

      inventory.htmx = Array.from(document.querySelectorAll("[hx-get], [hx-post], [hx-put], [hx-delete]")).map((el) => ({
        tag: el.tagName,
        hxGet: el.getAttribute("hx-get"),
        hxPost: el.getAttribute("hx-post"),
      }));

      return inventory;
    });

    test.info().annotations.push({
      type: "element-inventory",
      description: [
        `Pipelines: ${discovered.pipelines.length}`,
        `Forms: ${discovered.forms.length}`,
        `Buttons: ${discovered.buttons.length}`,
        `Selects: ${discovered.selects.length}`,
        `Textareas: ${discovered.textareas.length}`,
        `CSRF tokens: ${discovered.csrfTokens}`,
        `HTMX elements: ${discovered.htmx.length}`,
        `Pipeline names: ${discovered.pipelines.map((p: any) => p.name).join(", ")}`,
      ].join("\n"),
    });

    // ── 2. Verify pipeline data integrity ──
    expect(discovered.pipelines.length).toBeGreaterThanOrEqual(3);
    for (const p of discovered.pipelines) {
      expect(p.name).toBeTruthy();
      expect(p.status).toBeTruthy();
      expect(["idle", "running", "success", "error", "failed", "succeeded"]).toContain(p.status);
    }

    // ── 3. Verify CSRF protection on destructive forms ──
    const destructiveForms = discovered.forms.filter(
      (f: any) => f.action.includes("/delete/") || f.action.includes("/run")
    );
    expect(destructiveForms.length).toBeGreaterThanOrEqual(1);
    expect(discovered.csrfTokens).toBeGreaterThanOrEqual(1);

    // ── 4. Pipeline search ──
    const searchInput = page.locator("#pipe-search");
    if (await searchInput.isVisible()) {
      await searchInput.fill("bronze");
      await page.waitForTimeout(300);
      const visiblePipes = await page.locator('.pipe-item:not([style*="display: none"])').count();
      const bronzeCount = discovered.pipelines.filter((p: any) => p.name.includes("bronze")).length;
      const allPipes = await page.locator(".pipe-item").count();
      if (bronzeCount > 0 && bronzeCount < allPipes) {
        expect(visiblePipes).toBe(bronzeCount);
      }
      await searchInput.fill("");
      await page.waitForTimeout(300);
    }

    // ── 5. Pipeline selection (click first pipeline, verify DAG panel updates) ──
    const pipeItem = page.locator('[data-name]').first();
    if (await pipeItem.isVisible()) {
      const pipeName = await pipeItem.getAttribute("data-name");
      await pipeItem.click();
      await page.waitForTimeout(500);

      // Verify the DAG / detail panel shows something
      const dagName = page.locator("#dag-name");
      if (await dagName.isVisible()) {
        const dagText = await dagName.textContent();
        expect(dagText).toBeTruthy();
      }
      // Run form should now target this pipeline
      const runForm = page.locator("#run-form");
      if (await runForm.isVisible()) {
        const action = await runForm.getAttribute("action");
        expect(action).toContain(`/data/pipelines/run/${pipeName}`);
      }
    }

    // ── 6. Open pipeline wizard, explore each step ──
    const addBtn = page.locator("#add-pipeline");
    if (await addBtn.isVisible()) {
      await addBtn.click();
      await page.waitForTimeout(300);

      // Wizard should be open — verify step indicators
      const modal = page.locator("#add-pipeline-modal, [x-show*='pwiz']").first();
      if (await modal.isVisible({ timeout: 2000 }).catch(() => false)) {
        // Find and click transform builder buttons
        const transformBtns = page.locator('#pwiz-transforms button, [x-data*="pwiz"] button[data-tip]');
        const btnCount = await transformBtns.count();
        let clicked = 0;
        for (let i = 0; i < btnCount; i++) {
          const btn = transformBtns.nth(i);
          if (await btn.isVisible()) {
            const text = await btn.textContent();
            const tip = await btn.getAttribute("data-tip");
            // Skip navigation buttons (Back, Cancel, Next, Create)
            if (tip && !["← Back", "Cancel", "Next", "Create pipeline"].includes(tip)) {
              await btn.click();
              await page.waitForTimeout(200);
              clicked++;
            }
          }
        }
        test.info().annotations.push({
          type: "wizard-interaction",
          description: `Clicked ${clicked} transform builder buttons in the wizard`,
        });

        // Test the schedule preset selector
        const schedSelect = page.locator("#pwiz-sched, select[name='schedule']").first();
        if (await schedSelect.isVisible()) {
          const opts = await schedSelect.locator("option").allTextContents();
          if (opts.length > 2) {
            await schedSelect.selectOption({ index: 1 });
          }
        }

        // Close the modal
        const cancelBtn = page.locator("button:has-text('Cancel')").first();
        if (await cancelBtn.isVisible()) {
          await cancelBtn.click();
          await page.waitForTimeout(200);
        }
      }
    }

    // ── 7. Schedule preset selector (outside wizard) ──
    const scheduleSelect = page.locator("select.form-select, select.input").first();
    if (await scheduleSelect.isVisible() && await scheduleSelect.isEnabled()) {
      const opts = await scheduleSelect.locator("option").allTextContents();
      if (opts.length > 2) {
        await scheduleSelect.selectOption({ index: 1 });
        await page.waitForTimeout(200);
      }
    }

    // ── 8. DAG canvas / pipeline detail tabs ──
    const tabs = page.locator(".tabs .tab, [class*='tab']");
    const tabCount = await tabs.count();
    for (let i = 0; i < Math.min(tabCount, 4); i++) {
      const tab = tabs.nth(i);
      if (await tab.isVisible() && await tab.isEnabled()) {
        await tab.click();
        await page.waitForTimeout(200);
      }
    }

    // ── 9. Verify API status endpoint responds ──
    const statusResp = await page.request.get("/data/pipelines/status");
    if (statusResp.ok()) {
      const data = await statusResp.json();
      expect(Array.isArray(data)).toBe(true);
      test.info().annotations.push({
        type: "api-status",
        description: `GET /data/pipelines/status -> ${statusResp.status()} with ${data.length} pipelines`,
      });
    }

    // ── 10. Assertions ──
    if (consoleErrors.length) {
      test.info().annotations.push({
        type: "console-errors",
        description: consoleErrors.join("\n"),
      });
    }
    if (networkErrors.length) {
      test.info().annotations.push({
        type: "network-errors",
        description: networkErrors.map((e) => `[${e.status}] ${e.url}`).join("\n"),
      });
    }

    expect(consoleErrors).toEqual([]);
    expect(networkErrors).toEqual([]);
  });
});
