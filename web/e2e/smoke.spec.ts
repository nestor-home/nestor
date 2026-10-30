import { expect, test } from "@playwright/test";

test("the journal opens and shows why the assistant spoke", async ({ page }) => {
  await page.goto("/journal");
  await expect(page.getByRole("heading", { name: "Journal", level: 1 })).toBeVisible();
  await expect(page.getByText(/^pourquoi :/).first()).toBeVisible();
});

test("every section of the navigation answers", async ({ page }) => {
  await page.goto("/journal");
  const nav = page.getByRole("navigation", { name: "Sections" });
  for (const name of [
    "Connexions",
    "Satellites",
    "Tâches",
    "Veilles",
    "Souvenirs",
    "Personnes",
    "Comptes",
    "Système",
  ]) {
    await nav.getByRole("link", { name }).click();
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
  }
});
