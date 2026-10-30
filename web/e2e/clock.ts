import { test as base } from "@playwright/test";

export { expect } from "@playwright/test";

/**
 * The mock household's day is relative to "now" (events minutes ago, "today" since midnight): every
 * test on the mocks starts at the same hour of the same day, the clock flowing from there.
 */
export const test = base.extend<{ fixedDay: undefined }>({
  fixedDay: [
    async ({ page }, use) => {
      await page.clock.install({ time: new Date(2026, 9, 30, 18, 30) });
      await use(undefined);
    },
    { auto: true },
  ],
});
