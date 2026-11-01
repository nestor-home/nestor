/**
 * The mock household is written in English, the server's default language. A French reader gets
 * it in French: every text the mock owns (room names, messages, memories, labels) is written once
 * with its French beside it, `fr("living room", "salon")`, and an answer to a French reader swaps
 * each such text. One dataset, two languages; what someone types in the admin stays as typed.
 */
const FRENCH = new Map<string, string>();

/** An English text of the mock and its French; returns the English, the stored value. */
export function fr(english: string, french: string): string {
  FRENCH.set(english, french);
  return english;
}

/** Codes, never words: an `owner` role or a `completed` status stays as the API defines it. */
const CODES = new Set(["id", "role", "status", "risk", "kind", "type", "health", "tone", "subject", "auth", "slot"]);

/** A value as the mock server sends it to a French reader. */
export function inFrench<T>(value: T): T {
  if (typeof value === "string") return (FRENCH.get(value) ?? value) as T;
  if (Array.isArray(value)) return value.map(inFrench) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [k, CODES.has(k) && typeof v === "string" ? v : inFrench(v)]),
    ) as T;
  }
  return value;
}
