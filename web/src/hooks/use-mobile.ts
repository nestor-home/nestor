import { useCallback, useEffect, useState } from "react";

const MOBILE_BREAKPOINT = 768;

/** Below `md`: the rail becomes a tab bar under the thumb, and sheets take the screen. */
export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.innerWidth < MOBILE_BREAKPOINT,
  );
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const media = matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);
    const update = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    media.addEventListener("change", update);
    update();
    return () => media.removeEventListener("change", update);
  }, []);
  return isMobile;
}

const WIDE_BREAKPOINT = 1024;
const FOLDED = "nestor.rail.folded";

/**
 * Whether the rail shows names beside its icons: from `lg`, unless the person folded it (remembered on this
 * device). Below `lg` it is icons only and cannot unfold.
 */
export function useRail(): { wide: boolean; roomy: boolean; toggle: () => void } {
  const [roomy, setRoomy] = useState(() => typeof window !== "undefined" && window.innerWidth >= WIDE_BREAKPOINT);
  const [folded, setFolded] = useState(() => {
    try {
      return localStorage.getItem(FOLDED) === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const media = matchMedia(`(min-width: ${WIDE_BREAKPOINT}px)`);
    const update = () => setRoomy(window.innerWidth >= WIDE_BREAKPOINT);
    media.addEventListener("change", update);
    update();
    return () => media.removeEventListener("change", update);
  }, []);
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
