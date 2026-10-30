import "@testing-library/jest-dom/vitest";
import { act, cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach } from "vitest";
import { setCsrfToken } from "@/api";
import { reset } from "@/mocks/db";
import { server } from "@/mocks/server";

// Node's fetch has no page to resolve `/api/v1/...` against: give it jsdom's origin
const nodeFetch = globalThis.fetch;
globalThis.fetch = (input, init) =>
  nodeFetch(typeof input === "string" && input.startsWith("/") ? new URL(input, location.origin) : input, init);

// the first render of a whole route compiles lazily: give it time
configure({ asyncUtilTimeout: 4000 });

// the household's admin reads French: tests run in French unless one switches
Object.defineProperty(window.navigator, "languages", { value: ["fr-FR", "fr"], configurable: true });
Object.defineProperty(window.navigator, "language", { value: "fr-FR", configurable: true });

// jsdom has no scrolling; the router restores scroll positions
window.scrollTo = () => undefined;
Element.prototype.scrollIntoView = () => undefined;
// cmdk measures its list; jsdom has no layout, so observing is a no-op
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
// the character's animation loop has nothing to show in jsdom: tests run as with reduced motion
globalThis.matchMedia ??= ((query: string) => ({
  matches: query.includes("prefers-reduced-motion"),
  media: query,
  onchange: null,
  addEventListener: () => undefined,
  removeEventListener: () => undefined,
  addListener: () => undefined,
  removeListener: () => undefined,
  dispatchEvent: () => false,
})) as typeof globalThis.matchMedia;
// no canvas in jsdom: the dither texture simply does not draw
HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext;

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
beforeEach(() => {
  reset();
  setCsrfToken(null);
  sessionStorage.clear();
});
/**
 * Any React warning, console.error or console.warn fails the test that caused it: a missing part
 * of a compound component, a bad nesting or an act() leak shows up here before it ships.
 * Allowed: noise we cannot fix from here, each with its reason.
 */
const ALLOWED = [
  // Base UI finishes its own open/close transitions and tab indicator on timers after the
  // interaction: updates inside its primitives, not ours (our components still fail the test)
  /not wrapped in act.*\b(?:TabsList|DialogRoot|DialogPopup|DialogBackdrop|AlertDialogRoot)\b/s,
  // jsdom predates the HTML <search> element that every current browser knows
  /tag <%s> is unrecognized in this browser.*\bsearch\b/,
];
const complaints: string[] = [];
for (const level of ["error", "warn"] as const) {
  const original = console[level].bind(console);
  console[level] = (...args: unknown[]) => {
    const text = args.map((a) => (a instanceof Error ? a.message : String(a))).join(" ");
    if (!ALLOWED.some((re) => re.test(text))) complaints.push(`console.${level}: ${text.slice(0, 500)}`);
    original(...args);
  };
}

afterEach(async () => {
  // let the closing transitions of Base UI popups finish inside act(), as a browser would
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
  cleanup();
  server.resetHandlers();
  const found = complaints.splice(0);
  if (found.length) throw new Error(`The test printed warnings or errors:\n${found.join("\n")}`);
});
afterAll(() => server.close());
