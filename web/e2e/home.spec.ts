import { expect, test } from "@playwright/test";

/** The home on the mocks, at phone and desktop widths: the agent, the house, the day, no sideways scroll. */
for (const width of [390, 1440]) {
  test(`the home at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 600 ? 844 : 900 });
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator("svg.nestor").first()).toBeVisible();
    const house = page.getByRole("region", { name: "La maison" });
    await expect(house).toBeVisible();
    await expect(page.getByRole("list", { name: "Aujourd'hui" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    // a room leads to what happened there
    await house.getByRole("link", { name: /^Salon/ }).click();
    await expect(page).toHaveURL(/\/journal\?room=salon/);
  });
}
