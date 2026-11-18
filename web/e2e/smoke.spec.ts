import { expect, test } from "./clock";

test("the journal opens and shows why the assistant spoke", async ({ page }) => {
  await page.goto("/journal");
  await expect(page.getByRole("heading", { name: "Journal", level: 1 })).toBeVisible();
  await expect(page.getByText(/^why:/).first()).toBeVisible();
});

test("every space of the navigation answers", async ({ page }) => {
  await page.goto("/journal");
  const nav = page.getByRole("navigation", { name: "Sections" });
  for (const [space, heading] of [
    ["Talk", /^Write to/],
    ["Ongoing", "Ongoing"],
    ["The house", "The house"],
    ["Settings", "Settings"],
    ["Today", /Hello|Good evening|Good night|Good morning/],
  ] as const) {
    await nav.getByRole("link", { name: new RegExp(`^${space}`) }).click();
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
  }
});

test("settings lead to everything the installation is made of", async ({ page }) => {
  for (const name of ["Connections", "Satellites", "Accounts", "Configuration", "System"]) {
    await page.goto("/settings");
    await page.getByRole("link", { name: new RegExp(`^${name}`) }).click();
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
  }
});
