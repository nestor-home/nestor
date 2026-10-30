/**
 * The active locale and translator, for code that formats outside React's tree (dates, counts,
 * error messages). The provider sets them and re-renders the app under a new key on change, so
 * every render reads the current ones.
 */
import type { FluentVariable } from "@fluent/bundle";
import { ReactLocalization } from "@fluent/react";
import { bundleFor, DEFAULT_LOCALE, type Locale } from "./catalog";

export type Args = Record<string, FluentVariable>;

/** The server's catalogues by locale, once fetched (`GET /i18n/{locale}`). */
const serverSources = new Map<Locale, string>();

let locale: Locale = DEFAULT_LOCALE;
let l10n = localizationFor(DEFAULT_LOCALE);

export function setServerCatalogue(of: Locale, source: string): void {
  serverSources.set(of, source);
}

export function localizationFor(next: Locale): ReactLocalization {
  const bundle = (l: Locale) => bundleFor(l, serverSources.get(l) ?? "");
  const bundles = next === DEFAULT_LOCALE ? [bundle(next)] : [bundle(next), bundle(DEFAULT_LOCALE)];
  return new ReactLocalization(bundles);
}

export function activate(next: Locale): ReactLocalization {
  locale = next;
  l10n = localizationFor(next);
  return l10n;
}

export function activeLocale(): Locale {
  return locale;
}

/** A message of the admin's catalogue; its id when missing (the catalogue test catches that). */
export function tr(id: string, args?: Args): string {
  return l10n.getString(id, args ?? null, id);
}

export function hasMessage(id: string): boolean {
  return l10n.getBundle(id) !== null;
}
