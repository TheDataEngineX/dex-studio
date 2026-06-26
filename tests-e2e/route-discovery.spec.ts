import { test, expect } from "@playwright/test";

test.describe("autonomous route discovery", () => {
  test("crawl all routes and validate responses", async ({ page }) => {
    const failed: { route: string; status: number; text: string }[] = [];
    const missingAssets: { url: string; status: number }[] = [];
    const visitedRoutes = new Set<string>();

    page.on("response", (resp) => {
      if (resp.status() === 404) {
        missingAssets.push({ url: resp.url(), status: resp.status() });
      }
    });

    const queue = ["/"];
    while (queue.length > 0) {
      const route = queue.shift()!;
      if (visitedRoutes.has(route)) continue;
      visitedRoutes.add(route);

      const resp = await page.goto(route, { waitUntil: "load" });
      const status = resp?.status() ?? 0;
      if (status >= 400) {
        failed.push({ route, status, text: (await page.textContent("body"))?.slice(0, 200) ?? "" });
        continue;
      }

      const hrefs = await page.locator("a[href]").evaluateAll((els) =>
        els
          .map((el) => (el as HTMLAnchorElement).getAttribute("href"))
          .filter(
            (h): h is string =>
              !!h && h.startsWith("/") && !h.startsWith("//") && !h.includes("/static/") && !h.includes("/favicon")
          )
      );
      for (const h of hrefs) {
        if (!visitedRoutes.has(h)) queue.push(h);
      }

      if (visitedRoutes.size > 120) break;
    }

    test.info().annotations.push({
      type: "routes",
      description: `crawled ${visitedRoutes.size} routes: ${[...visitedRoutes].sort().join(", ")}`,
    });
    if (missingAssets.length) {
      test.info().annotations.push({
        type: "missing-assets",
        description: missingAssets.map((a) => `${a.status} ${a.url}`).join("\n"),
      });
    }

    expect(failed).toEqual([]);
  });
});
