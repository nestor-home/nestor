import { describe, expect, it } from "vitest";
import type { JournalItem } from "@/api";
import { liveItem } from "@/test/render";
import { buildStories, type Chain, type Thread } from "./stories";

let minute = 0;
const at = () => new Date(Date.UTC(2026, 9, 30, 9, minute++)).toISOString();
const ev = (overrides: Partial<JournalItem>) => liveItem({ at: at(), ...overrides });

describe("stories", () => {
  it("threads a conversation: each turn with its tool call, answer and what it started", () => {
    const s = { session: "s-1" };
    const items = [
      ev({ id: "u", type: "conversation.user_turn", kind: "conversation", links: { ...s, turn: "t1" } }),
      ev({
        id: "c1",
        type: "tools.tool_called",
        kind: "tool",
        tool: "mail_search",
        links: { ...s, turn: "t1", call: "k" },
      }),
      ev({
        id: "c2",
        type: "tools.tool_completed",
        kind: "tool",
        tool: "mail_search",
        outcome: { ok: true, duration_s: 0.8 },
        links: { ...s, turn: "t1", call: "k" },
      }),
      ev({ id: "ts", type: "cognition.task_started", kind: "task", links: { ...s, turn: "t1", task: "T" } }),
      ev({ id: "a", type: "conversation.assistant_turn", kind: "conversation", links: { ...s, turn: "t1" } }),
      ev({ id: "te", type: "cognition.task_ended", kind: "task", links: { task: "T" } }),
    ];
    const stories = buildStories(items);
    expect(stories.map((st) => st.key)).toEqual(["task:T", "session:s-1"]);
    const thread = stories[1] as Thread;
    expect(thread.turns).toHaveLength(1);
    const [turn] = thread.turns;
    expect(turn?.user?.id).toBe("u");
    expect(
      turn?.steps.map((st) => (st.type === "call" ? `call:${st.call.ended?.id}` : `${st.type}:${st.item.id}`)),
    ).toEqual(["call:c2", "spawn:ts", "event:a"]);
  });

  it("chains a watch from its trigger to the follow-up, wherever the steps were said", () => {
    const w = { watch: "W" };
    const items = [
      ev({ id: "trig", type: "initiative.watch_triggered", kind: "watch", links: w }),
      ev({ id: "cons", type: "initiative.delivery_considered", kind: "delivery", links: { ...w, delivery: "d" } }),
      ev({
        id: "said",
        type: "initiative.delivered",
        kind: "delivery",
        channels: ["voice"],
        links: { ...w, delivery: "d" },
      }),
      ev({
        id: "relance",
        type: "initiative.delivered",
        kind: "delivery",
        channels: ["whatsapp"],
        links: { ...w, delivery: "d" },
      }),
    ];
    const [chain] = buildStories(items) as Chain[];
    expect(chain?.subject).toEqual({ type: "watch", id: "W" });
    expect(chain?.items.map((i) => i.id)).toEqual(["trig", "cons", "said", "relance"]);
  });

  it("orders stories by their latest event and keeps lone events alone", () => {
    const items = [
      ev({ id: "old", type: "home.presence_changed", kind: "presence", links: {} }),
      ev({ id: "t1", type: "conversation.user_turn", kind: "conversation", links: { session: "s", turn: "x" } }),
      ev({ id: "mid", type: "satellites.person_detected", kind: "observation", links: {} }),
      ev({ id: "t2", type: "conversation.assistant_turn", kind: "conversation", links: { session: "s", turn: "x" } }),
    ];
    expect(buildStories(items).map((s) => s.key)).toEqual(["session:s", "event:mid", "event:old"]);
  });

  it("starts a thread mid-way when its first turn is on an older page", () => {
    const items = [
      ev({ id: "a", type: "conversation.assistant_turn", kind: "conversation", links: { session: "s", turn: "x" } }),
    ];
    const [thread] = buildStories(items) as Thread[];
    expect(thread?.turns[0]?.user).toBeNull();
  });
});
