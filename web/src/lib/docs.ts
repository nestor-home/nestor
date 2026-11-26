import type { Locale } from "@/i18n/catalog";

const SITE = "https://nestorhome.dev";

/**
 * A page of Nestor's documentation, from its slug (`tools#search`), in the reader's language. The section is kept in
 * English only: its anchor is the English heading's.
 */
export function docsUrl(slug: string, locale: Locale): string {
  const [page, section] = slug.split("#");
  const path = page === "index" ? "" : `${page}/`;
  if (locale !== "en") return `${SITE}/${locale}/docs/${path}`;
  return `${SITE}/docs/${path}${section ? `#${section}` : ""}`;
}
