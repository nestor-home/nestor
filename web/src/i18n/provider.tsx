import { LocalizationProvider } from "@fluent/react";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { browserLocale, DEFAULT_LOCALE, isLocale, type Locale } from "./catalog";

const fetched = new Map<Locale, Promise<string>>();

/** Once per locale and page: the server's catalogue in Fluent syntax. */
function fetchCatalogue(locale: Locale): Promise<string> {
  let pending = fetched.get(locale);
  if (!pending) {
    pending = fetch(`/api/v1/i18n/${locale}`, { credentials: "same-origin" }).then((r) => (r.ok ? r.text() : ""));
    fetched.set(locale, pending);
  }
  return pending;
}

import { activate, setServerCatalogue } from "./runtime";

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

const LocaleContext = createContext<LocaleState | null>(null);

/**
 * Fluent for the whole admin. The locale is the account's (`/me.locale`) once signed in, the
 * browser's best match before; `<html lang>` follows it.
 */
export function I18nProvider({ children, initial }: { children: ReactNode; initial?: Locale }) {
  const [locale, setLocale] = useState<Locale>(() => initial ?? browserLocale());
  const [loaded, setLoaded] = useState(0); // bumps when a server catalogue arrives
  // biome-ignore lint/correctness/useExhaustiveDependencies: `loaded` rebuilds the bundles with it
  const l10n = useMemo(() => activate(locale), [locale, loaded]);

  // the server's own messages (journal lines, reasons, errors) in this locale and the default one
  useEffect(() => {
    let cancelled = false;
    for (const wanted of new Set<Locale>([locale, DEFAULT_LOCALE])) {
      fetchCatalogue(wanted).then(
        (text) => {
          if (cancelled || !text) return;
          setServerCatalogue(wanted, text);
          setLoaded((n) => n + 1);
        },
        () => undefined, // without it, the server's rendered `text` is shown as it came
      );
    }
    return () => {
      cancelled = true;
    };
  }, [locale]);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const set = useCallback((next: Locale) => setLocale(next), []);
  const value = useMemo(() => ({ locale, setLocale: set }), [locale, set]);
  return (
    <LocaleContext.Provider value={value}>
      <LocalizationProvider l10n={l10n}>
        <LocaleKey locale={locale}>{children}</LocaleKey>
      </LocalizationProvider>
    </LocaleContext.Provider>
  );
}

/** Remounts what is below on a locale change: formatting helpers outside React then agree. */
function LocaleKey({ locale, children }: { locale: Locale; children: ReactNode }) {
  return (
    <div key={locale} className="contents">
      {children}
    </div>
  );
}

export function useLocale(): LocaleState {
  const state = useContext(LocaleContext);
  if (!state) throw new Error("useLocale outside I18nProvider");
  return state;
}

/** Follows the signed-in account's locale when it has one. */
export function useAccountLocale(accountLocale: string | null | undefined): void {
  const { locale, setLocale } = useLocale();
  useEffect(() => {
    if (isLocale(accountLocale) && accountLocale !== locale) setLocale(accountLocale);
  }, [accountLocale, locale, setLocale]);
}
