import axe from "axe-core";
import { expect } from "vitest";

/**
 * No accessibility violation in the page as rendered: names, roles, labels, nesting of
 * interactive elements, ARIA wiring of compound components. Contrast needs real layout and
 * colours, which jsdom lacks; Playwright covers how things look.
 */
export async function expectAccessible(root: Element = document.body): Promise<void> {
  const result = await axe.run(root, {
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  const violations = result.violations.map(
    (v) => `${v.id}: ${v.help}\n  ${v.nodes.map((n) => n.html.slice(0, 160)).join("\n  ")}`,
  );
  expect(violations).toEqual([]);
}
