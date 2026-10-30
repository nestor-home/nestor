import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type ThemeChoice = "system" | "light" | "dark";
type Resolved = "light" | "dark";

const STORAGE_KEY = "nestor.theme";

interface ThemeState {
  choice: ThemeChoice;
  resolved: Resolved;
  choose: (choice: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

function stored(): ThemeChoice {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

function systemDark(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * Follows the system unless the person picked a side. The resolved theme lands on
 * `<html data-theme>`, which flips `color-scheme` and therefore every token (tokens.css).
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoice] = useState<ThemeChoice>(stored);
  const [dark, setDark] = useState(systemDark);

  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const media = matchMedia("(prefers-color-scheme: dark)");
    const update = () => setDark(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  const resolved: Resolved = choice === "system" ? (dark ? "dark" : "light") : choice;

  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
  }, [resolved]);

  const choose = useCallback((next: ThemeChoice) => {
    setChoice(next);
    try {
      if (next === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // private browsing: the choice lasts for this page only
    }
  }, []);

  const value = useMemo(() => ({ choice, resolved, choose }), [choice, resolved, choose]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const state = useContext(ThemeContext);
  if (!state) throw new Error("useTheme outside ThemeProvider");
  return state;
}
