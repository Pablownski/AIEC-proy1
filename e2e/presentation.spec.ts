import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { metadata, wireReply } from "../packages/chat-widget/tests/presentation-fixture";

async function fixtures(context: BrowserContext) {
  // Public reference navigation is fulfilled locally: never contact providers in E2E.
  await context.route("https://www.imdb.com/**", (route) => route.fulfill({ contentType: "text/html", body: "<title>IMDb local fixture</title><p>Referencia IMDb simulada</p>" }));
  await context.route("https://books.google.com/**", (route) => route.fulfill({ contentType: "text/html", body: "<title>Books local fixture</title><p>Referencia Books simulada</p>" }));
  await context.route("https://image.tmdb.org/**", (route) => route.fulfill({ contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=", "base64") }));
}

test("multiple cards, missing poster and mobile layout", async ({ page, context }) => {
  await fixtures(context);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.route("**/api/v1/chat", (route) => route.fulfill({ json: { ...wireReply,
    message: { ...wireReply.message, metadata: { ...metadata, actions: [], books: [], comparisons: [],
      movies: [metadata.movies[0], { ...metadata.movies[0], id: 12, title: "Segunda película", poster_url: null,
        source_url: "https://www.themoviedb.org/movie/12" }] } } } }));
  await page.goto("/");
  await page.getByLabel("Escribe un mensaje").fill("Recomiéndame películas");
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect(page.getByRole("article", { name: /Película:/ })).toHaveCount(2);
  await expect(page.getByLabel("Póster no disponible para Segunda película")).toBeVisible();
  expect(await page.locator("body").evaluate((body) => body.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.getByAltText("TMDB", { exact: true }).evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await page.screenshot({ path: "test-results/catalog-mobile.png", fullPage: true });
});

test("real Chromium opens both verified tabs when popups are allowed and avoids duplicates", async ({ page, context }) => {
  await fixtures(context);
  const opened: Page[] = [];
  context.on("page", (popup) => opened.push(popup));
  await page.route("**/api/v1/chat", (route) => route.fulfill({ json: wireReply }));
  await page.goto("/");
  await page.getByLabel("Escribe un mensaje").fill("Compárala con su libro");
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect(page.getByLabel("Comparación libro y película")).toBeVisible();
  await expect.poll(() => opened.filter((p) => !p.isClosed()).map((p) => p.url()).sort()).toEqual(metadata.actions.map((a) => a.url).sort());
  for (const popup of opened.filter((p) => !p.isClosed())) expect(await popup.evaluate(() => window.opener)).toBeNull();
  await page.getByLabel("Escribe un mensaje").fill("Compara otra vez");
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect(page.getByLabel("Comparación libro y película")).toHaveCount(2);
  await expect.poll(() => opened.filter((p) => !p.isClosed()).length).toBe(2);
  await page.screenshot({ path: "test-results/comparison-desktop.png", fullPage: true });
});

test.describe("Chromium with its default popup policy enabled", () => {
  test("automates what the browser permits and offers all remaining references", async () => {
    const { chromium } = await import("@playwright/test");
    const browser = await chromium.launch({ ignoreDefaultArgs: ["--disable-popup-blocking"] });
    const context = await browser.newContext();
    const page = await context.newPage();
    await fixtures(context);
    const opened: Page[] = [];
    context.on("page", (popup) => opened.push(popup));
    await page.route("**/api/v1/chat", (route) => route.fulfill({ json: wireReply }));
    await page.goto(process.env.E2E_BASE_URL ?? "http://localhost:3000");
    await page.getByLabel("Escribe un mensaje").fill("Compárala con su libro");
    await page.getByRole("button", { name: "Enviar mensaje" }).click();
    await expect(page.getByLabel("Comparación libro y película")).toBeVisible();
    await expect.poll(async () => {
      const auto = opened.filter((p) => !p.isClosed()).map((p) => p.url());
      const links = await page.locator(".agichat-reference-fallback a").evaluateAll((nodes) => nodes.map((a) => (a as HTMLAnchorElement).href));
      return [...auto, ...links].sort();
    }).toEqual(metadata.actions.map((a) => a.url).sort());
    console.log(`Chromium popup policy: automatic=${opened.filter((p) => !p.isClosed()).length}; fallback=${await page.locator(".agichat-reference-fallback a").count()}`);
    await browser.close();
  });
});

test("unused reservations close after a text-only response", async ({ page, context }) => {
  const opened: Page[] = [];
  context.on("page", (popup) => opened.push(popup));
  await page.route("**/api/v1/chat", (route) => route.fulfill({ json: { ...wireReply,
    message: { ...wireReply.message, metadata: null } } }));
  await page.goto("/");
  await page.getByLabel("Escribe un mensaje").fill("Compara referencias");
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect(page.getByText("Aquí está la comparación.")).toBeVisible();
  await expect.poll(() => opened.filter((p) => !p.isClosed()).length).toBe(0);
});

test("closed reservations offer working isolated fallback links in a real browser", async ({ page, context }) => {
  await fixtures(context);
  const opened: Page[] = [];
  context.on("page", (popup) => opened.push(popup));
  let release: (() => void) | undefined;
  const wait = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/chat", async (route) => { await wait; await route.fulfill({ json: wireReply }); });
  await page.goto("/");
  await page.getByLabel("Escribe un mensaje").fill("Compárala con su libro");
  await page.getByRole("button", { name: "Enviar mensaje" }).click();
  await expect.poll(() => opened.length).toBe(2);
  for (const popup of [...opened]) await popup.close();
  release!();
  const fallback = page.getByRole("link", { name: "Abrir IMDb", exact: true });
  await expect(fallback).toBeVisible();
  const popupPromise = context.waitForEvent("page");
  await fallback.click();
  const popup = await popupPromise;
  await popup.waitForURL(metadata.actions[0]!.url);
  expect(await popup.evaluate(() => window.opener)).toBeNull();
});
