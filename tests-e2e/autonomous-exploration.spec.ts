import { test, expect } from "@playwright/test";

test.describe("autonomous exploration", () => {
  test("discover pages, find htmx endpoints, validate dynamic content", async ({ page }) => {
    test.setTimeout(60_000);

    const htmxErrors: { route: string; url: string; status: number }[] = [];
    const consoleErrors: string[] = [];
    const discovered: { route: string; title: string; htmx: string[] }[] = [];

    page.on("response", (resp) => {
      // 404s from API-like paths are worth reporting
      if (resp.status() === 404 && resp.url().includes("/api/")) {
        htmxErrors.push({ route: page.url(), url: resp.url(), status: resp.status() });
      }
    });
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    const routes = [
      "/", "/data/pipelines", "/data/transforms", "/data/streaming",
      "/data/watermarks", "/data/backfill", "/intelligence/playground",
      "/intelligence/models", "/intelligence/predictions", "/system/status",
      "/system/components", "/system/alerting", "/system/compaction",
      "/system/settings", "/system/runs",
    ];

    for (const route of routes) {
      await page.goto(route, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(500);

      const title = await page.title();
      const htmxAttrs = await page.locator("[hx-get], [hx-post], [hx-put], [hx-delete]").evaluateAll((els) =>
        els.map((el) => {
          const href = (el as HTMLElement).getAttribute("hx-get")
            || (el as HTMLElement).getAttribute("hx-post")
            || (el as HTMLElement).getAttribute("hx-put")
            || (el as HTMLElement).getAttribute("hx-delete");
          return href || "";
        }).filter(Boolean)
      );

      discovered.push({ route, title, htmx: htmxAttrs });

      // Trigger each hx-GET endpoint and validate it responds
      const getTriggers = await page.locator("[hx-get]").evaluateAll((els) =>
        els.map((el) => (el as HTMLElement).getAttribute("hx-get")).filter(Boolean)
      );
      for (const url of [...new Set(getTriggers)].slice(0, 3)) {
        const resp = await page.request.get(url);
        if (resp.status() >= 400) {
          htmxErrors.push({ route, url, status: resp.status() });
        }
      }
    }

    test.info().annotations.push({
      type: "discovered-htmx-endpoints",
      description: discovered
        .map((d) => `${d.route}: ${d.title}\n  htmx: ${d.htmx.join(", ") || "none"}`)
        .join("\n\n"),
    });
    if (htmxErrors.length) {
      test.info().annotations.push({
        type: "htmx-errors",
        description: htmxErrors.map((e) => `[${e.status}] ${e.url} (from ${e.route})`).join("\n"),
      });
    }
    if (consoleErrors.length) {
      test.info().annotations.push({
        type: "console-errors",
        description: consoleErrors.join("\n"),
      });
    }

    expect(htmxErrors).toEqual([]);
  });
});
