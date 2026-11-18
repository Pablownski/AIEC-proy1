import { expect, test } from "@playwright/test";
import { wireReply } from "../packages/chat-widget/tests/presentation-fixture";

test("approved local sprites animate in Chromium and preserve the structured response", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 360, height: 800 });
  const assets = new Set<string>();
  page.on("response", (response) => {
    if (/\/(idle|talk_[12]|think_[1-4]|done|error)\.[^/]*png/.test(response.url()) && response.ok()) {
      assets.add(response.url());
    }
  });
  await page.route("https://image.tmdb.org/**", (route) => route.fulfill({ contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=", "base64") }));
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/chat", async (route) => {
    await waiting;
    await route.fulfill({ json: wireReply });
  });
  await page.goto("/");
  const avatar = page.locator(".agichat-avatar");
  const image = avatar.locator("img");
  await expect(avatar).toHaveAttribute("data-state", "idle");
  await expect(image).toHaveJSProperty("naturalWidth", 418);
  await expect(image).toHaveCSS("image-rendering", "pixelated");
  await expect.poll(() => assets.size).toBe(9);
  const initialBox = await avatar.boundingBox();
  await page.getByLabel("Escribe un mensaje").fill("Recomienda una película");
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect(avatar).toHaveAttribute("data-state", "thinking");
  const frame = await image.getAttribute("src");
  await expect.poll(() => image.getAttribute("src")).not.toBe(frame);
  expect(await avatar.boundingBox()).toEqual(initialBox);
  release();
  await expect(avatar).toHaveAttribute("data-state", "talking");
  await expect(page.locator(".agichat-message-preview")).toBeVisible();
  await expect(avatar).toHaveAttribute("data-state", "done");
  await expect(page.getByLabel("Comparación libro y película")).toBeVisible();
  await expect(image).toHaveJSProperty("naturalWidth", 418);
  expect(await avatar.boundingBox()).toEqual(initialBox);
  await page.screenshot({ path: testInfo.outputPath("damian-mobile.png"), fullPage: true });
  await expect(avatar).toHaveAttribute("data-state", "idle", { timeout: 5000 });
});

test("real browser error recovers to idle and a new request interrupts the error", async ({ page }) => {
  let attempt = 0;
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/chat", async (route) => {
    if (++attempt === 1) { await route.fulfill({ status: 503 }); return; }
    await waiting;
    await route.fulfill({ json: { ...wireReply, message: { ...wireReply.message, metadata: null } } });
  });
  await page.goto("/");
  const avatar = page.locator(".agichat-avatar");
  await page.getByLabel("Escribe un mensaje").fill("Hola");
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect(avatar).toHaveAttribute("data-state", "error");
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(avatar).toHaveAttribute("data-state", "thinking");
  // Cross the previous error's deadline: it must not replace the pending state.
  await page.clock.install();
  await page.clock.runFor(3100);
  await expect(avatar).toHaveAttribute("data-state", "thinking");
  release();
  await expect(avatar).toHaveAttribute("data-state", "done", { timeout: 8000 });
  await expect(page.locator(".agichat-error")).not.toBeVisible();
});

test("reduced motion uses static frames and immediate complete Markdown", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/v1/chat", (route) => route.fulfill({ json: {
    ...wireReply, message: { ...wireReply.message, content: "## Respuesta completa", metadata: null },
  } }));
  await page.goto("/");
  await page.getByLabel("Escribe un mensaje").fill("Hola");
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect(page.getByRole("heading", { name: "Respuesta completa" })).toBeVisible();
  await expect(page.locator(".agichat-message-preview")).toHaveCount(0);
  await expect(page.locator(".agichat-avatar")).toHaveAttribute("data-state", "done");
});
