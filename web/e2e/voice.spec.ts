import { expect, test } from "./clock";

/**
 * Recording a voice in a real browser, both themes: the mock API's microphone (mocks/microphone.ts)
 * goes through the real capture (AudioWorklet), end-of-phrase detection, resampling and WAV encoding,
 * which the mock server checks as Nestor does (16-bit mono at 16 kHz).
 */
test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => sessionStorage.clear());
});

test("records a voice from consent to a try", async ({ page }, info) => {
  test.setTimeout(90_000);
  await page.goto("/people/jules");
  await page.getByRole("button", { name: "Record their voice" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Record Jules's voice" })).toBeVisible();
  await page.screenshot({ path: info.outputPath("1-consent.png") });

  await dialog.getByRole("button", { name: "Start" }).click();
  await expect(dialog.getByText("I can hear you well.")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: info.outputPath("2-microphone.png") });
  await dialog.getByRole("button", { name: "Continue" }).click();

  await expect(dialog.getByText("That was a bit short. Once more?")).toBeVisible({ timeout: 20_000 });
  await page.screenshot({ path: info.outputPath("3-phrase-again.png") });
  await expect(dialog.getByRole("heading", { name: "I recognise Jules's voice" })).toBeVisible({ timeout: 40_000 });
  await dialog.getByRole("button", { name: "Try it" }).click();
  await expect(dialog.getByText("It's Jules.")).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: info.outputPath("4-done.png") });

  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("button", { name: "Record again" })).toBeVisible();
});

test("fills the whole screen on a phone and keeps Tab inside", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/people/jules");
  await page.getByRole("button", { name: "Record their voice" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Start" })).toBeVisible();
  await page.waitForTimeout(300); // its opening transition
  expect(await dialog.boundingBox()).toEqual({ x: 0, y: 0, width: 390, height: 844 });
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    await page.waitForTimeout(80); // Base UI sends focus back in from its guards on the next frame
    const where = await dialog.evaluate(
      (d) => d.contains(document.activeElement) || document.activeElement?.hasAttribute("data-base-ui-focus-guard"),
    );
    expect(where).toBe(true);
  }
  await page.screenshot({ path: info.outputPath("phone.png") });
});
