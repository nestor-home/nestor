import { expect, type Page, test } from "@playwright/test";

/**
 * Against a real Nestor, through the dev server's proxy or the built admin it serves:
 *   NESTOR_URL=http://localhost:5198 E2E_LOGIN=owner E2E_PASSWORD=… pnpm e2e:live
 * Use a throwaway instance (its own data_dir): these tests register an OAuth client and create
 * invitations.
 */
const login = process.env.E2E_LOGIN ?? "owner";
const password = process.env.E2E_PASSWORD ?? "";

test.describe.configure({ mode: "serial" });
test.skip(!password, "E2E_PASSWORD is not set");

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel(/Identifiant|Login/).fill(login);
  await page.getByLabel(/Mot de passe|Password/).fill(password);
  await page.getByRole("button", { name: /Se connecter|Sign in/ }).click();
  await expect(page.getByRole("navigation", { name: "Sections" })).toBeVisible();
}

test("signs in and refuses a wrong password", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/Identifiant|Login/).fill(login);
  await page.getByLabel(/Mot de passe|Password/).fill("not the password");
  await page.getByRole("button", { name: /Se connecter|Sign in/ }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await signIn(page);
});

test("the journal loads and filters by kind", async ({ page }) => {
  await signIn(page);
  await page.goto("/journal");
  await expect(page.getByRole("heading", { name: "Journal", level: 1 })).toBeVisible();
  await expect(page.getByText(/événements?|events?$/).first()).toBeVisible();
  await page.getByRole("button", { name: /^(Type|Kind)/ }).click();
  const option = page.locator("[cmdk-item]").first();
  const label = (await option.locator("span.flex-1").textContent())?.trim() ?? "";
  await option.click();
  await expect(page).toHaveURL(/kinds=/);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: new RegExp(label) }).first()).toBeVisible();
});

test("connecting Gmail goes as far as the provider's consent page", async ({ page }) => {
  await signIn(page);
  await page.goto("/connections/catalogue?connect=google");
  const sheet = page.getByRole("dialog", { name: "Gmail" });
  await expect(sheet).toBeVisible();
  const register = sheet.getByRole("button", {
    name: /Enregistrer le client|Register the client|Remplacer le client|Replace the client/,
  });
  await register.click();
  const dialog = page.getByRole("dialog", { name: /client OAuth|OAuth client/ });
  await dialog.getByLabel(/client ID/).fill("e2e-client.apps.googleusercontent.com");
  await dialog.getByLabel(/client secret/).fill("e2e-secret");
  await dialog.getByRole("button", { name: /Enregistrer le client|Register the client/ }).click();
  await expect(dialog).toBeHidden();
  // the consent page is Google's: stop the navigation there and check where it was going
  let consent = "";
  await page.route(/accounts\.google\.com/, async (route) => {
    consent = route.request().url();
    await route.abort();
  });
  await sheet.getByRole("button", { name: /^(Connecter|Connect)$/ }).click();
  await expect.poll(() => consent, { timeout: 10_000 }).toMatch(/^https:\/\/accounts\.google\.com\//);
  expect(consent).toContain("client_id=e2e-client.apps.googleusercontent.com");
  expect(consent).toContain("redirect_uri=");
});

test("satellites: the approvals page answers", async ({ page }) => {
  await signIn(page);
  await page.goto("/satellites");
  await expect(page.getByRole("heading", { name: "Satellites", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Appairés|Paired/ })).toBeVisible();
});

test("an invitation is created and its link handed over once", async ({ page }) => {
  await signIn(page);
  await page.goto("/accounts");
  await page.getByRole("button", { name: /Inviter…|Invite…/ }).click();
  const dialog = page.getByRole("dialog");
  // a member's account belongs to a person of the household (the server says so if forgotten)
  await dialog.getByRole("button", { name: /Créer l'invitation|Create the invitation/ }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  const person = dialog.getByRole("combobox", { name: /Personne du foyer|Household person/ });
  await person.fill("Lé");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await dialog.getByRole("button", { name: /Créer l'invitation|Create the invitation/ }).click();
  await expect(dialog.getByRole("button", { name: /Copier le lien|Copy the invitation link/ })).toBeVisible();
  const link = await dialog.locator("code").first().textContent();
  expect(link).toMatch(/invitation/);
});

test("the language switches from French to English and back, server texts included", async ({ page }) => {
  await signIn(page);
  await page.goto("/journal");
  const menu = page.getByRole("button", { name: /Menu du compte|Account menu/ });
  await menu.click();
  await page.getByRole("menuitemradio", { name: "English" }).click();
  await expect(page.getByRole("link", { name: "Today" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.getByRole("button", { name: /Account menu/ }).click();
  await page.getByRole("menuitemradio", { name: "Français" }).click();
  await expect(page.getByRole("link", { name: "Aujourd'hui" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
});

/** Renames the agent through the configuration, restarts it by hand, and checks the new name is live. */
async function rename(page: Page, from: string, to: string) {
  await page.goto("/config/persona");
  const name = page.getByRole("textbox", { name: /^(Nom|Name)$/ });
  await expect(name).toHaveValue(from);
  await name.fill(to);
  const bar = page.getByRole("region", { name: /Modifications non enregistrées|Unsaved changes/ });
  await expect(bar.getByRole("button", { name: /1 modification|1 change/ })).toBeVisible();
  await bar.getByRole("button", { name: /^(Enregistrer|Save)$/ }).click();
  await expect(page.getByText(/Redémarrage requis|Restart required/)).toBeVisible();
  // saved, not applied: the running agent keeps its name until a person restarts it
  await expect(page.getByRole("link", { name: new RegExp(from) }).first()).toBeVisible();
  await page.getByRole("button", { name: /Redémarrer…|Restart…/ }).click();
  await page.getByRole("button", { name: /Redémarrer maintenant|Restart now/ }).click();
  await expect(page.getByText(/Je redémarre, à tout de suite|Restarting, back in a moment/)).toBeVisible();
  // sessions live in the process's memory: the new process asks to sign in again, then comes back here
  await expect(page.getByRole("heading", { name: /Connexion|Sign in/ })).toBeVisible({ timeout: 60_000 });
  await page.getByLabel(/Identifiant|Login/).fill(login);
  await page.getByLabel(/Mot de passe|Password/).fill(password);
  await page.getByRole("button", { name: /Se connecter|Sign in/ }).click();
  await expect(page).toHaveURL(/\/config\/persona$/);
  await expect(page.getByRole("textbox", { name: /^(Nom|Name)$/ })).toHaveValue(to);
  await expect(page.getByText(/Redémarrage requis|Restart required/)).toBeHidden();
  await expect(page.getByRole("link", { name: new RegExp(`^${to}`) }).first()).toBeVisible();
}

test("a configuration change applies once a person restarts", async ({ page }) => {
  test.setTimeout(150_000);
  await signIn(page);
  await page.goto("/config/persona");
  const current = await page.getByRole("textbox", { name: /^(Nom|Name)$/ }).inputValue();
  const next = current === "Alfred" ? "Alfred Pennyworth" : "Alfred";
  await rename(page, current, next);
  await rename(page, next, current); // leave the throwaway instance as it was
});
