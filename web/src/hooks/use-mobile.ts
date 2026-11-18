import { useCallback, useState, useSyncExternalStore } from "react";

/** Whether a media query holds, following it as the window changes (false where there is no `matchMedia`). */
function useMedia(query: string): boolean {
  const subscribe = useCallback(
    (changed: () => void) => {
      if (typeof matchMedia !== "function") return () => {};
      const media = matchMedia(query);
      media.addEventListener("change", changed);
      return () => media.removeEventListener("change", changed);
    },
    [query],
  );
  return useSyncExternalStore(subscribe, () => typeof matchMedia === "function" && matchMedia(query).matches);
}

/** Below `md`: the rail becomes a tab bar under the thumb, and sheets take the screen. */
export function useIsMobile(): boolean {
  return useMedia("(max-width: 767px)");
}
const FOLDED = "nestor.rail.folded";

/**
 * Whether the rail shows names beside its icons: from `lg`, unless the person folded it (remembered on this
 * device). Below `lg` it is icons only and cannot unfold.
 */
export function useRail(): { wide: boolean; roomy: boolean; toggle: () => void } {
  const roomy = useMedia("(min-width: 1024px)");
  const [folded, setFolded] = useState(() => {
    try {
      return localStorage.getItem(FOLDED) === "1";
    } catch {
      return false;
    }
  });
  const toggle = useCallback(() => {
    setFolded((was) => {
      try {
        localStorage.setItem(FOLDED, was ? "0" : "1");
      } catch {
        // storage unavailable: the choice lasts until the next reload
      }
      return !was;
    });
  }, []);
  return { wide: roomy && !folded, roomy, toggle };
}
