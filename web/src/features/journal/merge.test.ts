import { describe, expect, it } from "vitest";
import { liveItem } from "@/test/render";
import { matches, merge } from "./merge";

describe("matches", () => {
  const item = liveItem({ kind: "delivery", people: ["lea"], channels: ["whatsapp"], room: "salon" });

  it("keeps an item every filter accepts", () => {
    expect(matches(item, {})).toBe(true);
    expect(matches(item, { kinds: ["delivery", "task"], person: "lea", channel: "whatsapp", room: "salon" })).toBe(
      true,
    );
  });

  it("drops an item any filter refuses", () => {
    expect(matches(item, { kinds: ["tool"] })).toBe(false);
    expect(matches(item, { person: "mathis" })).toBe(false);
    expect(matches(item, { channel: "voice" })).toBe(false);
    expect(matches(item, { room: "bureau" })).toBe(false);
    expect(matches(item, { q: "colis" })).toBe(false);
  });
});

describe("merge", () => {
  it("puts live items with the loaded ones, newest first, each id once", () => {
    const old = liveItem({ id: "a", at: "2026-10-30T09:00:00Z" });
    const loaded = liveItem({ id: "b", at: "2026-10-30T10:00:00Z" });
    const arrived = liveItem({ id: "c", at: "2026-10-30T11:00:00Z" });
    expect(merge([arrived, loaded], [loaded, old]).map((l) => l.id)).toEqual(["c", "b", "a"]);
  });
});
