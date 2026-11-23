import { type ClassValue, clsx } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/** tailwind-merge, told about the type scale of `styles/app.css`: `text-body` is a size, not a colour. */
const twMerge = extendTailwindMerge({
  extend: {
    theme: { text: ["micro", "meta", "body", "lead", "heading", "title", "sheet"] },
    classGroups: { "font-size": ["title-card", "title-item", "title-sub", "title-sheet"] },
  },
});

/** Joins class names, letting later Tailwind utilities override earlier ones. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** A random id of 32 hex digits. `crypto.randomUUID` exists only on https; the admin is often reached over http. */
export function randomId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** A name as a title starts: a room (`salon` → `Salon`), a day from `Intl`. */
export function capital(s: string): string {
  return s.charAt(0).toLocaleUpperCase() + s.slice(1);
}
