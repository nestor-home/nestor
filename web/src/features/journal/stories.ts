/**
 * The journal as stories instead of a flat log, built only from the ids events carry:
 * - a thread is one conversation (`links.session`): each user turn with what it caused — tool
 *   calls (paired by `links.call`), the answer, an interruption, a memory — in order;
 * - a chain follows one subject through its steps: a task (started → progress → ended →
 *   delivered), a watch (triggered → triaged → announced → followed up) or a lone delivery;
 * - anything else stays a single event.
 * Stories are ordered by their latest event, so a story that moves comes back to the top.
 */
import type { Id, JournalItem } from "@/api";

export interface ToolCall {
  call: Id;
  name: string;
  started: JournalItem | null;
  ended: JournalItem | null;
}

export type Step =
  | { type: "event"; item: JournalItem }
  | { type: "call"; call: ToolCall }
  | { type: "spawn"; item: JournalItem }; // started a story of its own (a task, a watch)

export interface Turn {
  id: Id;
  user: JournalItem | null; // null when the thread starts mid-way (older page not loaded)
  steps: Step[];
}

interface Common {
  key: string;
  latest: string; // ISO time of the latest event
  earliest: string;
  items: JournalItem[]; // oldest first
}

export interface Thread extends Common {
  type: "thread";
  session: Id;
  turns: Turn[];
}

export interface Chain extends Common {
  type: "chain";
  subject: { type: "task" | "watch" | "delivery"; id: Id };
}

export interface Single extends Common {
  type: "single";
  item: JournalItem;
}

export type Story = Thread | Chain | Single;

const CONVERSATIONAL = new Set(["conversation", "tool", "memory"]);

/** Which story an event belongs to. Tasks and watches win over the conversation they came from. */
export function storyKey(item: JournalItem): string {
  const { links } = item;
  if (links.session && CONVERSATIONAL.has(item.kind) && !links.task) return `session:${links.session}`;
  if (links.task) return `task:${links.task}`;
  if (links.watch) return `watch:${links.watch}`;
  if (links.delivery) return `delivery:${links.delivery}`;
  if (links.session) return `session:${links.session}`;
  return `event:${item.id}`;
}

const byTime = (a: JournalItem, b: JournalItem) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0);

export function buildStories(items: readonly JournalItem[]): Story[] {
  const groups = new Map<string, JournalItem[]>();
  for (const item of items) {
    const key = storyKey(item);
    const group = groups.get(key);
    if (group) group.push(item);
    else groups.set(key, [item]);
  }
  // what a turn started elsewhere, shown in the conversation as a reference
  const spawned = new Map<Id, JournalItem[]>();
  for (const item of items) {
    const turn = item.links.turn;
    if (!turn || storyKey(item).startsWith("session:")) continue;
    if (!item.type.endsWith("_started") && !item.type.endsWith("_created")) continue;
    spawned.set(turn, [...(spawned.get(turn) ?? []), item]);
  }

  const stories: Story[] = [];
  for (const [key, group] of groups) {
    const sorted = [...group].sort(byTime);
    const common = {
      key,
      items: sorted,
      earliest: sorted[0]?.at ?? "",
      latest: sorted.at(-1)?.at ?? "",
    };
    const [type, id = ""] = key.split(/:(.*)/s) as [string, string?];
    if (type === "session") stories.push({ ...common, type: "thread", session: id, turns: turnsOf(sorted, spawned) });
    else if (type === "task" || type === "watch" || type === "delivery")
      stories.push({ ...common, type: "chain", subject: { type, id } });
    else if (sorted[0]) stories.push({ ...common, type: "single", item: sorted[0] });
  }
  return stories.sort((a, b) => (a.latest < b.latest ? 1 : a.latest > b.latest ? -1 : 0));
}

function turnsOf(items: JournalItem[], spawned: Map<Id, JournalItem[]>): Turn[] {
  const turns: Turn[] = [];
  const calls = new Map<Id, ToolCall>();
  let current: Turn | null = null;
  for (const item of items) {
    const isUser = item.type.endsWith("user_turn");
    const turnId = item.links.turn ?? item.id;
    if (isUser || !current || (item.links.turn && item.links.turn !== current.id)) {
      current = { id: turnId, user: isUser ? item : null, steps: [] };
      turns.push(current);
      if (isUser) {
        for (const spawn of spawned.get(turnId) ?? []) current.steps.push({ type: "spawn", item: spawn });
        continue;
      }
    }
    const callId = item.links.call;
    if (callId && item.kind === "tool") {
      let call = calls.get(callId);
      if (!call) {
        call = { call: callId, name: item.tool ?? item.text, started: null, ended: null };
        calls.set(callId, call);
        current.steps.push({ type: "call", call });
      }
      if (item.outcome) call.ended = item;
      else call.started = item;
      continue;
    }
    current.steps.push({ type: "event", item });
  }
  // spawned items sort among the steps by time
  for (const turn of turns) turn.steps.sort((a, b) => stepTime(a).localeCompare(stepTime(b)));
  return turns;
}

function stepTime(step: Step): string {
  if (step.type === "call") return (step.call.started ?? step.call.ended)?.at ?? "";
  return step.item.at;
}

/** The people and channels a story involves, for its header. */
export function cast(story: Story): { people: Id[]; channels: string[]; rooms: string[] } {
  const people = new Set<Id>();
  const channels = new Set<string>();
  const rooms = new Set<string>();
  for (const item of story.items) {
    for (const p of item.people) people.add(p);
    for (const c of item.channels) channels.add(c);
    if (item.room) rooms.add(item.room);
  }
  return { people: [...people], channels: [...channels], rooms: [...rooms] };
}
