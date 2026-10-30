import { expect, test } from "./clock";

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

/** On a retina screen the dithered textures keep their box: the bitmap follows the box, never the reverse. */
test.describe("on a 2× screen", () => {
  test.use({ deviceScaleFactor: 2 });
  // the home's hero is the one dithered texture left (the satellites cards lost theirs)
  for (const path of ["/"]) {
    test(`the textures of ${path} keep their size`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator("canvas").first()).toBeAttached();
      await page.waitForTimeout(500); // several resize rounds, had the texture been growing
      const canvases = await page.locator("canvas").evaluateAll((all) =>
        all.map((c) => ({
          box: (c as HTMLCanvasElement).getBoundingClientRect().width,
          bitmap: (c as HTMLCanvasElement).width,
        })),
      );
      for (const { box, bitmap } of canvases) {
        expect(box).toBeLessThan(1440);
        expect(Math.abs(bitmap - box * 2)).toBeLessThanOrEqual(2);
      }
    });
  }
});
