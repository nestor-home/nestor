import type { Page } from "@playwright/test";
import { expect, test } from "./clock";

/**
 * No text pushes its box: every screen, and the main dialogs and sheets, on the stress fixture
 * (long URLs, unbroken ids, multi-line JSON, very long names) at phone and desktop widths. An
 * element fails when its content is wider than itself while it neither scrolls nor clips on
 * purpose (an ellipsis), or when the page scrolls sideways.
 */
const LONG_WORD = "Anticonstitutionnellementdéraisonnablementinextricablement-60";
const TASK = `t-${"0123456789abcdef".repeat(2)}`;
const WATCH = `w-${"fedcba9876543210".repeat(2)}`;

const ROUTES = [
  "/",
  "/journal",
  "/journal?density=compact",
  "/journal?session=s-stress",
  "/people",
  "/people/marie-amelie",
  "/memories",
  "/watches",
  `/watches/${WATCH}`,
  "/tasks",
  `/tasks/${TASK}`,
  "/connections",
  "/connections/c-gmail-mathis",
  "/connections/catalogue",
  "/satellites",
  "/satellites/reachy-salon",
  "/system",
  "/accounts",
  "/accounts/acc-mathis",
  "/config/persona",
  "/config/tools",
  "/config/secrets",
  "/config/history",
];

async function overflows(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const found: string[] = [];
    if (document.documentElement.scrollWidth > window.innerWidth + 1)
      found.push(`page scrolls sideways (${document.documentElement.scrollWidth} > ${window.innerWidth})`);
    const hidden = (el: Element) => {
      const style = getComputedStyle(el);
      return el.classList.contains("sr-only") || style.clip === "rect(0px, 0px, 0px, 0px)" || style.opacity === "0";
    };
    /** The horizontal extent of the text a box shows, outside what scrolls or clips on purpose. */
    const textExtent = (box: Element) => {
      let left = Number.POSITIVE_INFINITY;
      let right = Number.NEGATIVE_INFINITY;
      const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (!node.textContent?.trim()) continue;
        let parent = node.parentElement;
        let skip = false;
        while (parent && parent !== box) {
          const style = getComputedStyle(parent);
          if (hidden(parent) || style.display === "none" || style.overflowX !== "visible" || parent.closest("svg")) {
            skip = true;
            break;
          }
          parent = parent.parentElement;
        }
        if (skip) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const rect of range.getClientRects()) {
          if (!rect.width) continue;
          left = Math.min(left, rect.left);
          right = Math.max(right, rect.right);
        }
      }
      return { left, right };
    };
    for (const el of document.querySelectorAll<HTMLElement>("body *")) {
      if (el.closest("svg")) continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden" || el.clientWidth === 0 || hidden(el)) continue;
      if (el.scrollWidth <= el.clientWidth + 2) continue; // sub-pixel rounding
      if (style.overflowX === "auto" || style.overflowX === "scroll") continue; // scrolls on purpose
      if (style.textOverflow === "ellipsis") continue; // cut on purpose, the whole text on hover
      const box = el.getBoundingClientRect();
      const text = textExtent(el);
      // what overflows is decoration (a shadow, a rail, a figure's arc), not text: fine
      if (text.right <= box.right + 2 && text.left >= box.left - 2) continue;
      const name = `${el.tagName.toLowerCase()}.${String(el.className).split(" ").slice(0, 4).join(".")}`;
      found.push(`${name} ${el.scrollWidth}>${el.clientWidth}: ${el.textContent?.trim().slice(0, 50)}`);
    }
    // the opposite failure: a column squeezed by its neighbour until text stacks letter by letter
    for (const el of document.querySelectorAll<HTMLElement>("body *")) {
      if (el.closest("svg") || hidden(el)) continue;
      const own = [...el.childNodes]
        .filter((n) => n.nodeType === Node.TEXT_NODE)
        .map((n) => n.textContent ?? "")
        .join("")
        .trim();
      if (own.length < 12) continue;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      const em = Number.parseFloat(style.fontSize) || 16;
      const width = el.getBoundingClientRect().width;
      if (width > 0 && width < 3.5 * em) found.push(`squeezed to ${Math.round(width)}px: ${own.slice(0, 40)}`);
    }
    return found;
  });
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("nestor.mock.stress", "1");
  });
});

for (const width of [390, 1440]) {
  test.describe(`at ${width}px`, () => {
    test.use({ viewport: { width, height: width < 600 ? 844 : 900 } });

    for (const route of ROUTES) {
      test(`nothing overflows on ${route}`, async ({ page }) => {
        await page.goto(route);
        await page.waitForLoadState("networkidle");
        await page.waitForTimeout(400);
        expect(await overflows(page)).toEqual([]);
      });
    }

    test("nothing overflows in the journal's event sheet and an open conversation", async ({ page }) => {
      await page.goto("/journal?session=s-stress");
      await page.waitForLoadState("networkidle");
      await page
        .getByRole("button", { name: /Ce qui s'est passé/ })
        .first()
        .click();
      expect(await overflows(page)).toEqual([]);
      await page.locator("[data-journal-entry]").first().click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.waitForTimeout(300);
      expect(await overflows(page)).toEqual([]);
    });

    test("nothing overflows while adding a satellite", async ({ page }) => {
      await page.goto("/satellites");
      await page.getByRole("button", { name: "Ajouter un satellite" }).click();
      const sheet = page.getByRole("dialog", { name: "Ajouter un satellite" });
      await sheet.getByRole("button", { name: /^Configuration/ }).click();
      await sheet.getByLabel("Nom").fill(LONG_WORD);
      expect(await overflows(page)).toEqual([]);
      await sheet.getByRole("button", { name: "Commencer" }).click();
      await expect(sheet.getByRole("img", { name: /QR code/ })).toBeVisible();
      expect(await overflows(page)).toEqual([]);
    });

    test("nothing overflows in a component's sheet and the changes", async ({ page }) => {
      await page.goto("/config/tools");
      await page.getByRole("button", { name: `Modifier ${LONG_WORD}` }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.waitForTimeout(300);
      expect(await overflows(page)).toEqual([]);
    });
  });
}
