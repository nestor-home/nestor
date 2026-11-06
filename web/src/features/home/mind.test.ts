import { describe, expect, it } from "vitest";
import { liveItem } from "@/test/render";
import { marksOf } from "./mind";

const NOW = Date.parse("2026-10-30T15:00:00Z");
const at = (minutesAgo: number) => new Date(NOW - minutesAgo * 60_000).toISOString();

describe("the day's marks", () => {
  it("makes one mark per conversation, however many turns, and one per message delivered", () => {
    const items = [
      liveItem({ at: at(30), links: { session: "s1" }, people: [{ id: "lea", name: "Léa" }] }),
      liveItem({ at: at(29), type: "conversation.turn.assistant", links: { session: "s1" }, people: [] }),
      liveItem({ at: at(28), links: { session: "s1" }, people: [{ id: "jules", name: "Jules" }] }),
      liveItem({ at: at(10), type: "initiative.delivered", kind: "delivery", links: { delivery: "d1" } }),
      liveItem({ at: at(5), type: "agent.tool.called", kind: "tool" }),
    ];
    const marks = marksOf(items);
    expect(marks.map((m) => m.kind)).toEqual(["conversation", "delivery"]);
    expect(marks[0]).toMatchObject({ count: 3, people: ["lea", "jules"] });
  });
});
