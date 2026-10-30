/**
 * The admin's own messages (Project Fluent), one `.ftl` file per feature and locale under
 * `src/locales/<locale>/`. English is the default and the fallback; French is complete.
 * Messages the server owns (journal lines, reasons, errors) arrive rendered and are not here.
 */
import { FluentBundle, FluentResource } from "@fluent/bundle";
import { negotiateLanguages } from "@fluent/langneg";

export const LOCALES = ["en", "fr"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";

const SOURCES = import.meta.glob("../locales/*/*.ftl", { query: "?raw", import: "default", eager: true }) as Record<
  string,
  string
>;

/** The `.ftl` sources of one locale, by file name (for the catalogue tests). */
export function sourcesOf(locale: Locale): Record<string, string> {
  return Object.fromEntries(
    Object.entries(SOURCES)
      .filter(([path]) => path.includes(`/locales/${locale}/`))
      .map(([path, text]) => [path.split("/").at(-1) ?? path, text]),
  );
}

const cache = new Map<string, FluentBundle>();

/**
 * The bundle of a locale: the server's catalogue first when we have it (`GET /i18n/{locale}`,
 * every message the API sends, plugins' included), then the admin's own. On an id both define,
 * the server's wins: it is the one that knows what its arguments mean.
 */
export function bundleFor(locale: Locale, server = ""): FluentBundle {
  const key = `${locale}:${server.length}`;
  const cached = cache.get(key);
  if (cached) return cached;
  // no Unicode isolation marks around placeables: they would end up in titles and aria labels
  const bundle = new FluentBundle(locale, { useIsolating: false });
  if (server) bundle.addResource(new FluentResource(server));
  for (const [file, text] of Object.entries(sourcesOf(locale))) {
    const errors = bundle
      .addResource(new FluentResource(text))
      .filter((e) => !(server && /override an existing message/.test(e.message)));
    if (errors.length && import.meta.env.DEV) console.warn(`[i18n] ${locale}/${file}`, errors);
  }
  cache.set(key, bundle);
  return bundle;
}

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** The best of our locales for what the browser asks for. */
export function negotiate(requested: readonly string[]): Locale {
  const [best] = negotiateLanguages(requested, LOCALES, { defaultLocale: DEFAULT_LOCALE, strategy: "lookup" });
  return isLocale(best) ? best : DEFAULT_LOCALE;
}

export function browserLocale(): Locale {
  if (typeof navigator === "undefined") return DEFAULT_LOCALE;
  return negotiate(navigator.languages?.length ? navigator.languages : [navigator.language]);
}
