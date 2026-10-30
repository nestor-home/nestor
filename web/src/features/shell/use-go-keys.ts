import { useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import type { NavItem } from "./nav";

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/** `g` then a letter jumps to a section, like a terminal pager; ignored while typing. */
export function useGoKeys(items: readonly NavItem[]): void {
  const navigate = useNavigate();
  useEffect(() => {
    let armed = 0;
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (event.metaKey || event.ctrlKey || event.altKey || !target) return;
      if (TYPING.has(target.tagName) || target.isContentEditable) return;
      if (event.key === "g") {
        armed = Date.now();
        return;
      }
      if (Date.now() - armed > 1200) return;
      const item = items.find((i) => i.key === event.key);
      armed = 0;
      if (item) {
        event.preventDefault();
        void navigate({ to: item.to });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, navigate]);
}
