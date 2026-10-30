import { expect, type Locator, type Page, test } from "@playwright/test";

/**
 * The open state of each composite widget, in a real browser and both themes: exactly one item
 * highlighted, the pointer moves the highlight, and a dialog keeps Tab inside it.
 */
async function oneHighlighted(items: Locator, attribute: string) {
  const marked = items.locator(`xpath=self::*[@${attribute} and not(@${attribute}="false")]`);
  await expect(marked).toHaveCount(1);
  return marked;
}

async function hoverMoves(_page: Page, items: Locator, attribute: string) {
  const before = await (await oneHighlighted(items, attribute)).textContent();
  const count = await items.count();
  for (let i = 0; i < count; i++) {
    const item = items.nth(i);
    if ((await item.textContent()) === before) continue;
    await item.hover();
    await expect(await oneHighlighted(items, attribute)).toHaveText(((await item.textContent()) ?? "").trim());
    return;
  }
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => sessionStorage.clear());
});

test("select", async ({ page }, info) => {
  await page.goto("/accounts/acc-lea");
  await page.getByRole("combobox").first().click();
  const options = page.getByRole("listbox").getByRole("option");
  await page.keyboard.press("ArrowDown");
  await hoverMoves(page, options, "data-highlighted");
  await page.screenshot({ path: info.outputPath("select.png") });
});

test("combobox", async ({ page }, info) => {
  await page.goto("/connections/catalogue?connect=imap");
  await page.getByRole("combobox", { name: "Compte de" }).click();
  const options = page.getByRole("listbox").getByRole("option");
  await page.keyboard.press("ArrowDown");
  await hoverMoves(page, options, "data-highlighted");
  await page.screenshot({ path: info.outputPath("combobox.png") });
});

test("command palette", async ({ page }, info) => {
  await page.goto("/journal");
  await expect(page.getByRole("navigation", { name: "Sections" })).toBeVisible();
  await page.keyboard.press("ControlOrMeta+k");
  const items = page.getByRole("dialog").locator("[cmdk-item]");
  await hoverMoves(page, items, "data-selected");
  await page.screenshot({ path: info.outputPath("command.png") });
});

test("dropdown menu", async ({ page }, info) => {
  await page.goto("/journal");
  await page.getByRole("button", { name: /Menu du compte/ }).click();
  const items = page.getByRole("menu").locator("[role=menuitem], [role=menuitemradio]");
  await page.keyboard.press("ArrowDown");
  await hoverMoves(page, items, "data-highlighted");
  await page.screenshot({ path: info.outputPath("dropdown.png") });
});

test("popover with a command list", async ({ page }, info) => {
  await page.goto("/journal");
  await page.getByRole("button", { name: /^Personne/ }).click();
  const items = page.getByRole("dialog", { name: "Personne" }).locator("[cmdk-item]");
  await hoverMoves(page, items, "data-selected");
  await page.screenshot({ path: info.outputPath("popover.png") });
});

test("a dialog keeps Tab inside it and gives focus back on Escape", async ({ page }) => {
  await page.goto("/accounts");
  const open = page.getByRole("button", { name: "Inviter…" });
  await open.click();
  const dialog = page.getByRole("dialog", { name: "Inviter quelqu'un" });
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    // Base UI sends focus back in from its guards on the next frame: a person never tabs faster
    await page.waitForTimeout(80);
    // inside the dialog, or on one of Base UI's focus guards that send it back in
    const where = await dialog.evaluate(
      (d) => d.contains(document.activeElement) || document.activeElement?.hasAttribute("data-base-ui-focus-guard"),
    );
    expect(where).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(open).toBeFocused();
});
