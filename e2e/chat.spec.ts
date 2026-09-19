import { expect, test } from "@playwright/test";

test.describe("AGIChat widget — happy path", () => {
  test("user sends a message and sees the agent's markdown reply", async ({ page }) => {
    await page.goto("/");

    const widget = page.getByRole("region", { name: /Chat con/ });
    await expect(widget).toBeVisible();

    const input = page.getByLabel("Escribe un mensaje");
    await input.fill("Cuéntame sobre AGIChat");
    await input.press("Enter");

    await expect(page.getByText("Cuéntame sobre AGIChat")).toBeVisible();
    await expect(page.getByRole("heading", { name: "AGIChat" })).toBeVisible({ timeout: 10000 });
  });
});

test.describe("AGIChat widget — error path", () => {
  test("shows a friendly error and recovers after retry", async ({ page }) => {
    let firstAttempt = true;
    await page.route("**/api/v1/chat", async (route) => {
      if (firstAttempt) {
        firstAttempt = false;
        await route.fulfill({ status: 500, body: "Internal Server Error" });
        return;
      }
      await route.continue();
    });

    await page.goto("/");

    const input = page.getByLabel("Escribe un mensaje");
    await input.fill("Hola");
    await input.press("Enter");

    // Scoped to our own banner: Next.js injects its own role="alert" route
    // announcer into every page, which also matches a bare getByRole("alert").
    const errorBanner = page.locator(".agichat-error");
    await expect(errorBanner).toContainText("Intenta nuevamente");

    await page.getByRole("button", { name: "Reintentar" }).click();

    await expect(errorBanner).not.toBeVisible({ timeout: 10000 });
  });
});
