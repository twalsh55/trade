import type { APIRequestContext, Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

const mockApiBaseUrl = "http://127.0.0.1:8001";

async function resetMockApi(request: APIRequestContext) {
  await request.post(`${mockApiBaseUrl}/__reset`);
}

async function bootstrapSession(page: Page) {
  const response = await page.request.post("/api/session", {
    data: {
      sessionToken: "test-session-token",
    },
  });

  expect(response.ok()).toBeTruthy();
}

test.beforeEach(async ({ request }) => {
  await resetMockApi(request);
});

test("bootstraps a local app session and renders the authenticated dashboard shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();

  await bootstrapSession(page);
  await page.goto("/");

  await expect(page.getByText("Ada Lovelace", { exact: true })).toBeVisible();
  await expect(page.getByTestId("dashboard-benchmark-value")).toHaveText("SPY");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});

test("refreshes the dashboard with updated filters", async ({ page }) => {
  await bootstrapSession(page);
  await page.goto("/");

  await page.getByTestId("dashboard-benchmark-input").fill("QQQ");
  await page.getByTestId("dashboard-refresh-button").click();

  await expect(page.getByTestId("dashboard-status")).toHaveText("Dashboard refreshed.");
  await expect(page.getByTestId("dashboard-benchmark-value")).toHaveText("QQQ");
  await expect(page.getByText("Growth leadership")).toBeVisible();
});

test("saves settings and applies them back to the dashboard", async ({ page }) => {
  await bootstrapSession(page);
  await page.goto("/");

  await page.getByRole("heading", { name: "User dashboard defaults" }).scrollIntoViewIfNeeded();
  await page.getByTestId("settings-benchmark-input").fill("QQQ");
  await page.getByTestId("settings-save-button").click();

  await expect(page.getByTestId("settings-status")).toContainText("Settings saved.");
  await expect(page.getByTestId("dashboard-status")).toHaveText("Dashboard refreshed.");
  await expect(page.getByTestId("dashboard-benchmark-value")).toHaveText("QQQ");
});

test("refreshes the alert feed through the local proxy route", async ({ page }) => {
  await bootstrapSession(page);
  await page.goto("/");

  await expect(page.getByText("Baseline alert")).toBeVisible();

  await page.getByTestId("alerts-refresh-button").click();

  await expect(page.getByTestId("alerts-status")).toHaveText("Alert feed refreshed.");
  await expect(page.getByText("Refreshed alert feed")).toBeVisible();
});
