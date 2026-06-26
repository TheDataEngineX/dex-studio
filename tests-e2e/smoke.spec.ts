import { test, expect } from "@playwright/test";

test.describe("page smoke tests", () => {
  const pages: [string, RegExp][] = [
    ["/", /Hub/],
    ["/data/pipelines", /Pipelines/],
    ["/data/transforms", /Transforms/],
    ["/data/streaming", /Streaming/],
    ["/data/watermarks", /Watermarks/],
    ["/data/backfill", /Backfill/],
    ["/intelligence/playground", /Playground/],
    ["/intelligence/models", /Models/],
    ["/intelligence/predictions", /Predictions/],
    ["/system/status", /System Status/],
    ["/system/components", /Components/],
    ["/system/alerting", /Alerting/],
    ["/system/compaction", /Compaction/],
    ["/system/settings", /Settings/],
    ["/system/runs", /Runs/],
  ];

  for (const [route, titlePattern] of pages) {
    test(`loads ${route}`, async ({ page }) => {
      await page.goto(route, { waitUntil: "load" });
      await expect(page).toHaveURL(route);
      await expect(page).toHaveTitle(titlePattern);
      await expect(page.locator(".panel-item")).not.toHaveCount(0);
    });
  }
});
