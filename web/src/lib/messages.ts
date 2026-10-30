/** Server-owned texts (journal lines, reasons): our catalogue's wording when we have the id. */
import type { JournalItem, Rendered } from "@/api";
import { hasMessage, tr } from "@/i18n/runtime";

export function rendered(r: Rendered | null | undefined): string {
  if (!r) return "";
  return hasMessage(r.message.id) ? tr(r.message.id, r.message.args) : r.text;
}

/** What an event says happened. */
export function say(item: Pick<JournalItem, "message" | "text">): string {
  return rendered(item);
}

/** Why the assistant spoke up, or "" when the event has no reason. */
export function why(item: Pick<JournalItem, "reason">): string {
  return rendered(item.reason);
}
