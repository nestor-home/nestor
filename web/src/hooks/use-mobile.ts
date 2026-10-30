import { useEffect, useState } from "react";

const MOBILE_BREAKPOINT = 768;

/** Below `md`: the sidebar becomes a sheet opened from the top bar. */
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
