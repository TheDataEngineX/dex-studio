import { test as setup, expect } from "@playwright/test";

const AUTH_FILE = ".playwright/auth.json";
const PASSWORD = process.env.DEX_STUDIO_PASSPHRASE || "admin";

setup("authenticate", async ({ page }) => {
  await page.goto("/setup");
  if (page.url().includes("/login")) {
    await page.fill('input[name="passphrase"]', PASSWORD);
    await page.click('button[type="submit"]');
  } else {
    await page.fill('input[name="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/login/, { timeout: 10000 });
    await page.fill('input[name="passphrase"]', PASSWORD);
    await page.click('button[type="submit"]');
  }
  // 303 redirect may preserve POST — navigate explicitly to avoid 405
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/, { timeout: 10000 });
  await page.context().storageState({ path: AUTH_FILE });
});
