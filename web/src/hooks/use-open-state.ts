import { useState } from "react";

/**
 * An overlay's open state: its own, or the one a page hands it (`open`), which `onOpenChange` hears
 * change either way.
 */
export function useOpenState(open?: boolean, onOpenChange?: (open: boolean) => void) {
  const [own, setOwn] = useState(false);
  const setOpen = (next: boolean) => {
    setOwn(next);
    onOpenChange?.(next);
  };
  return [open ?? own, setOpen] as const;
}
