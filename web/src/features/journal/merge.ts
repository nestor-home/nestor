import type { JournalFilters, JournalItem } from "@/api";

/** Whether a live item belongs on the page the person is looking at (same rules as the API). */
export function matches(item: JournalItem, f: JournalFilters): boolean {
  const q = f.q?.toLowerCase();
  return (
    (!f.kinds?.length || f.kinds.includes(item.kind)) &&
    (!f.person || item.people.includes(f.person)) &&
    (!f.channel || item.channels.includes(f.channel)) &&
    (!f.room || item.room === f.room) &&
    (!q || `${item.text} ${item.detail} ${item.reason?.text ?? ""}`.toLowerCase().includes(q)) &&
    (!f.from || item.at >= f.from) &&
    (!f.to || item.at <= f.to) &&
    (!f.tone || item.tone === f.tone) &&
    (!f.session || item.links.session === f.session) &&
    (!f.conversation || item.links.conversation === f.conversation) &&
    (!f.task || item.links.task === f.task) &&
    (!f.watch || item.links.watch === f.watch) &&
    (!f.connection || item.links.connection === f.connection) &&
    (!f.satellite || item.links.satellite === f.satellite)
  );
}

/**
 * The items to show: live ones with the loaded pages, newest first, each id once.
 * The stream and the first page overlap when an item arrives while the page loads.
 */
export function merge(live: readonly JournalItem[], pages: readonly JournalItem[]): JournalItem[] {
  const seen = new Set<string>();
  const lines: JournalItem[] = [];
  for (const item of [...live, ...pages]) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    lines.push(item);
  }
  return lines.sort(newestFirst);
}

export function newestFirst(a: JournalItem, b: JournalItem): number {
  return a.at < b.at ? 1 : a.at > b.at ? -1 : 0;
}
