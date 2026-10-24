import { expect, test } from "@playwright/test";
import { E2E_API_TOKEN } from "../../playwright.config";

test("une question affiche la disposition citée, ses contrôles et les avertissements", async ({ page }) => {
  const seen: string[] = [];
  page.on("request", (r) => seen.push(JSON.stringify(r.headers()) + (r.postData() ?? "")));

  await page.goto("/");
  await expect(page.getByText("système d’intelligence artificielle")).toBeVisible();
  await page.getByLabel("Question").fill("inscription sur la liste des demandeurs d'emploi");
  await page.getByLabel("Date d’appréciation du droit (facultative)").fill("2026-10-24");
  await page.getByRole("button", { name: "Rechercher" }).click();

  const article = page.locator("article").first();
  await expect(article.getByRole("heading")).toContainText("Code du travail, article L5411-1");
  await expect(article.getByRole("heading")).toContainText("LEGIARTI000048590205");
  await expect(article.locator("blockquote")).toContainText("Est inscrite sur la liste des demandeurs d'emploi");
  await expect(article.getByText("PASSAGE_PRESENT — passage trouvé")).toBeVisible();
  await expect(page.getByText("Citation vérifiée avec réserves").first()).toBeVisible();
  await expect(page.getByText("Ne constitue pas une consultation juridique", { exact: false }).last()).toBeVisible();

  // Le jeton d'accès est ajouté par le serveur web et n'apparaît jamais côté navigateur.
  const last = await (await page.request.get("http://127.0.0.1:8099/__last")).json();
  expect(last.authorization).toBe(`Bearer ${E2E_API_TOKEN}`);
  expect(last.body).toEqual({ question: "inscription sur la liste des demandeurs d'emploi", as_of: "2026-10-24" });
  expect(seen.join("\n")).not.toContain(E2E_API_TOKEN);
  expect(await page.content()).not.toContain(E2E_API_TOKEN);
});

test("une question trop courte est refusée sans appeler l'API", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Question").fill("ab");
  await page.getByRole("button", { name: "Rechercher" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "question invalide" })).toBeVisible();
  // Refus par le serveur web : la question n'est jamais transmise à l'API.
  const last = await (await page.request.get("http://127.0.0.1:8099/__last")).json();
  expect(last?.body?.question).not.toBe("ab");
});

test("les en-têtes de sécurité sont présents", async ({ request }) => {
  const response = await request.get("/");
  const headers = response.headers();
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["referrer-policy"]).toBe("no-referrer");
  expect(headers["x-powered-by"]).toBeUndefined();
});
