import { describe, expect, it } from "vitest";
import { liveItem } from "@/test/render";
import { agentState, isQuiet, marksOf, merge, quietHours } from "./mind";

const at = (minutesAgo: number, now = Date.parse("2026-10-30T15:00:00Z")) =>
  new Date(now - minutesAgo * 60_000).toISOString();
const NOW = Date.parse("2026-10-30T15:00:00Z");

describe("the agent's state", () => {
  it("listens, thinks, speaks, then rests or works", () => {
    expect(agentState([liveItem({ at: at(0.1), type: "conversation.turn.user" })], 0, NOW)).toBe("listening");
    expect(agentState([liveItem({ at: at(0.1), type: "agent.tool.called", kind: "tool" })], 0, NOW)).toBe("thinking");
    expect(agentState([liveItem({ at: at(0.05), type: "conversation.turn.assistant" })], 0, NOW)).toBe("speaking");
    // nothing recent: what runs decides
    expect(agentState([liveItem({ at: at(10), type: "conversation.turn.assistant" })], 0, NOW)).toBe("idle");
    expect(agentState([liveItem({ at: at(10), type: "conversation.turn.assistant" })], 2, NOW)).toBe("working");
    expect(agentState([], 0, NOW)).toBe("idle");
  });
});

describe("the day's marks", () => {
  it("makes one mark per conversation, however many turns, and one per message delivered", () => {
    const items = [
      liveItem({ at: at(30), links: { session: "s1" }, people: ["lea"] }),
      liveItem({ at: at(29), type: "conversation.turn.assistant", links: { session: "s1" }, people: [] }),
      liveItem({ at: at(28), links: { session: "s1" }, people: ["jules"] }),
      liveItem({ at: at(10), type: "initiative.delivered", kind: "delivery", links: { delivery: "d1" } }),
      liveItem({ at: at(5), type: "agent.tool.called", kind: "tool" }),
    ];
    const marks = marksOf(items);
    expect(marks.map((m) => m.kind)).toEqual(["conversation", "delivery"]);
    expect(marks[0]).toMatchObject({ count: 3, people: ["lea", "jules"] });
  });

  it("merges live items into the day without counting one twice", () => {
    const a = liveItem({ uid: "a", at: at(5) });
    const b = liveItem({ uid: "b", at: at(1) });
    expect(merge([a], [b, a]).map((i) => i.uid)).toEqual(["b", "a"]);
  });
});

describe("quiet hours", () => {
  it("reads a window across midnight", () => {
    const q = quietHours("22:30-07:30");
    expect(q).toEqual({ from: 22 * 60 + 30, to: 7 * 60 + 30 });
    if (!q) return;
    expect(isQuiet(q, 23 * 60)).toBe(true);
    expect(isQuiet(q, 6 * 60)).toBe(true);
    expect(isQuiet(q, 12 * 60)).toBe(false);
    expect(quietHours(null)).toBeNull();
    expect(quietHours("tonight")).toBeNull();
  });
});
