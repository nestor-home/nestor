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
      ev({ id: "u", type: "conversation.turn.user", kind: "conversation", links: { ...s, turn: "t1" } }),
      ev({
        id: "c1",
        type: "agent.tool.called",
        kind: "tool",
        tool: "mail_search",
        links: { ...s, turn: "t1", call: "k" },
      }),
      ev({
        id: "c2",
        type: "agent.tool.completed",
        kind: "tool",
        tool: "mail_search",
        outcome: { ok: true, duration_s: 0.8 },
        links: { ...s, turn: "t1", call: "k" },
      }),
      ev({ id: "ts", type: "task.started", kind: "task", links: { ...s, turn: "t1", task: "T" } }),
      ev({ id: "a", type: "conversation.turn.assistant", kind: "conversation", links: { ...s, turn: "t1" } }),
      ev({ id: "te", type: "task.ended", kind: "task", links: { task: "T" } }),
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

  it("threads a conversation by its turns, as the server stamps them on every event", () => {
    const c = { session: "telegram:42", conversation: "c1" };
    const said = (id: string, turn: string) =>
      ev({ id, type: "conversation.turn.user", kind: "conversation", links: { ...c, turn } });
    const items = [
      said("u1", "r1"),
      ev({
        id: "k1",
        type: "agent.tool.called",
        kind: "tool",
        tool: "task_status",
        links: { ...c, turn: "r1", call: "k" },
      }),
      ev({
        id: "k2",
        type: "agent.tool.completed",
        kind: "tool",
        tool: "task_status",
        outcome: { ok: true, duration_s: 0.4 },
        links: { ...c, turn: "r1", call: "k" },
      }),
      ev({ id: "a1", type: "conversation.turn.assistant", kind: "conversation", links: { ...c, turn: "r1" } }),
      said("u2", "r2"),
      ev({ id: "a2", type: "conversation.turn.assistant", kind: "conversation", links: { ...c, turn: "r2" } }),
      // another conversation of the same session: its own thread
      said("u3", "r3"),
    ];
    items[6] = { ...(items[6] as JournalItem), links: { session: "telegram:42", conversation: "c2", turn: "r3" } };
    const stories = buildStories(items);
    expect(stories.map((st) => st.key)).toEqual(["conversation:c2", "conversation:c1"]);
    const thread = stories[1] as Thread;
    expect(thread.filter).toEqual({ conversation: "c1" });
    expect(
      thread.turns.map((t) => [t.user?.id, t.steps.map((st) => (st.type === "call" ? "call" : st.item.id))]),
    ).toEqual([
      ["u1", ["call", "a1"]],
      ["u2", ["a2"]],
    ]);
  });

  it("reads records written before conversations: a message opens a turn, the session is the thread", () => {
    const s = { session: "voice:salon" };
    const items = [
      ev({ id: "u1", type: "conversation.turn.user", kind: "conversation", links: s }),
      ev({ id: "a1", type: "conversation.turn.assistant", kind: "conversation", links: s }),
      ev({ id: "u2", type: "conversation.turn.user", kind: "conversation", links: s }),
    ];
    const thread = buildStories(items)[0] as Thread;
    expect(thread.filter).toEqual({ session: "voice:salon" });
    expect(thread.turns.map((t) => [t.user?.id, t.steps.length])).toEqual([
      ["u1", 1],
      ["u2", 0],
    ]);
  });

  it("keeps a message before its reply when both happened in the same instant", () => {
    const now = at();
    const s = { session: "s-same", turn: "u-same" };
    const reply = ev({ id: "8", at: now, type: "conversation.turn.assistant", kind: "conversation", links: s });
    const message = ev({ id: "9", at: now, type: "conversation.turn.user", kind: "conversation", links: s });
    const thread = buildStories([reply, message])[0] as Thread;
    expect(thread.turns.map((t) => [t.user?.id, t.steps.length])).toEqual([["9", 1]]);
  });

  it("chains a watch from its trigger to the follow-up, wherever the steps were said", () => {
    const w = { watch: "W" };
    const items = [
      ev({ id: "trig", type: "watch.triggered", kind: "watch", links: w }),
      ev({ id: "cons", type: "initiative.considered", kind: "delivery", links: { ...w, delivery: "d" } }),
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
      ev({ id: "old", type: "presence.changed", kind: "presence", links: {} }),
      ev({ id: "t1", type: "conversation.turn.user", kind: "conversation", links: { session: "s", turn: "x" } }),
      ev({ id: "mid", type: "observation.person.detected", kind: "observation", links: {} }),
      ev({ id: "t2", type: "conversation.turn.assistant", kind: "conversation", links: { session: "s", turn: "x" } }),
    ];
    expect(buildStories(items).map((s) => s.key)).toEqual(["session:s", "event:mid", "event:old"]);
  });

  it("starts a thread mid-way when its first turn is on an older page", () => {
    const items = [
      ev({ id: "a", type: "conversation.turn.assistant", kind: "conversation", links: { session: "s", turn: "x" } }),
    ];
    const [thread] = buildStories(items) as Thread[];
    expect(thread?.turns[0]?.user).toBeNull();
  });
});
