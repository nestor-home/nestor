import { expect, test } from "./clock";

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
