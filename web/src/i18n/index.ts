import { useLocalization } from "@fluent/react";
import type { Args } from "./runtime";
import { tr } from "./runtime";

export { browserLocale, isLocale, LOCALES, type Locale, negotiate } from "./catalog";
export { I18nProvider, useAccountLocale, useLocale } from "./provider";
export { type Args, activeLocale, hasMessage, tr } from "./runtime";

/** The translator for a component; re-renders when the locale changes. */
export function useT(): (id: string, args?: Args) => string {
  useLocalization();
  return tr;
}
