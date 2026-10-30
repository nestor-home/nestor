import { expect, test } from "@playwright/test";

/** The home on the mocks, at phone and desktop widths: the agent's map, its day, no sideways scroll. */
for (const width of [390, 1440]) {
  test(`the agent's mind at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 600 ? 844 : 900 });
    await page.goto("/");
    const map = page.getByRole("region", { name: /Ce que .+ perçoit en ce moment/ });
    await expect(map).toBeVisible();
    await expect(map.getByRole("link", { name: /^salon : / }).locator("visible=true")).toHaveCount(1);
    await expect(page.getByRole("list", { name: /moments aujourd'hui/ })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    // a room on the map leads to what happened there
    await map
      .getByRole("link", { name: /^salon : / })
      .locator("visible=true")
      .click();
    await expect(page).toHaveURL(/\/journal\?room=salon/);
  });
}
