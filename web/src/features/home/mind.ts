/**
 * The agent's mind, read from what the API says: the household as it perceives it (rooms, devices,
 * people), what it reaches (channels, tasks, watches, connections), and the marks of its day. Pure:
 * the home renders it.
 */

import type { Component, Connection, JournalItem, Person, PersonRef, Satellite, Task, Watch } from "@/api";
import type { FigureState } from "@/components/agent-figure";
import { is } from "@/lib/events";

export type AgentState = FigureState;

// -- the household as the agent perceives it -------------------------------------------------------

export interface RoomNode {
  key: string; // "room:salon"
  room: string;
  people: Person[];
  satellites: Satellite[];
  active: number; // events in this room today
}

export interface MindInput {
  people: readonly Person[];
  satellites: readonly Satellite[];
  items: readonly JournalItem[]; // today's
}

/** The rooms that matter now: where devices are, where people are, where things happened today. */
export function roomsOf({ people, satellites, items }: MindInput, limit = 6): RoomNode[] {
  const rooms = new Map<string, RoomNode>();
  const room = (name: string) => {
    const found = rooms.get(name) ?? { key: `room:${name}`, room: name, people: [], satellites: [], active: 0 };
    rooms.set(name, found);
    return found;
  };
  for (const s of satellites) room(s.room).satellites.push(s);
  for (const p of people) if (p.presence?.home && p.presence.room) room(p.presence.room).people.push(p);
  for (const i of items) if (i.room) room(i.room).active += 1;
  const weight = (r: RoomNode) => r.people.length * 100 + r.satellites.length * 10 + r.active;
  return [...rooms.values()].sort((a, b) => weight(b) - weight(a) || a.room.localeCompare(b.room)).slice(0, limit);
}

/** People not in a known room: away, or home somewhere unknown. */
export function elsewhere(people: readonly Person[]): { away: Person[]; unknown: Person[]; homeNoRoom: Person[] } {
  return {
    away: people.filter((p) => p.presence?.home === false),
    unknown: people.filter((p) => p.presence?.home == null),
    homeNoRoom: people.filter((p) => p.presence?.home === true && !p.presence.room),
  };
}

export interface Reach {
  channels: Component[];
  tasks: Task[];
  watches: Watch[];
  connections: Connection[];
}

/** The node an event belongs to, to make it pulse when it arrives. */
export function nodeOf(item: JournalItem, satellites: readonly Satellite[]): string | null {
  if (item.links.task) return `task:${item.links.task}`;
  if (item.kind === "watch" || item.links.watch) return "watches";
  if (item.links.satellite) {
    const s = satellites.find((x) => x.id === item.links.satellite);
    if (s) return `room:${s.room}`;
  }
  if (item.room) return `room:${item.room}`;
  if (item.links.connection || item.kind === "connection") return "connections";
  if (item.channels.length) return "channels";
  return null;
}

// -- the day -------------------------------------------------------------------------------------

export type MarkKind = "conversation" | "delivery" | "task" | "watch" | "memory" | "problem";

export interface Mark {
  key: string;
  kind: MarkKind;
  at: string;
  /** Minutes since midnight, local time. */
  minute: number;
  item: JournalItem; // the first event of what it stands for
  count: number; // events it stands for (turns of a conversation)
  people: PersonRef[];
  channels: string[];
  room: string | null;
}

const minuteOf = (iso: string) => {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
};

/**
 * The day as marks: one per conversation (at its first turn), per message the agent delivered, per
 * task it started, per watch that fired, per thing it learnt, per failure.
 */
export function marksOf(items: readonly JournalItem[]): Mark[] {
  const sorted = [...items].sort((a, b) => a.at.localeCompare(b.at));
  const sessions = new Map<string, Mark>();
  const marks: Mark[] = [];
  const mark = (kind: MarkKind, item: JournalItem): Mark => ({
    key: `${kind}:${item.id}`,
    kind,
    at: item.at,
    minute: minuteOf(item.at),
    item,
    count: 1,
    people: [...item.people],
    channels: [...item.channels],
    room: item.room,
  });
  for (const item of sorted) {
    const talk = item.links.conversation ?? item.links.session;
    if (item.kind === "conversation" && talk) {
      const known = sessions.get(talk);
      if (known) {
        known.count += 1;
        for (const p of item.people) if (!known.people.some((k) => k.id === p.id)) known.people.push(p);
        continue;
      }
      const m = mark("conversation", item);
      sessions.set(talk, m);
      marks.push(m);
    } else if (is(item, "delivered")) marks.push(mark("delivery", item));
    else if (is(item, "taskStarted")) marks.push(mark("task", item));
    else if (is(item, "watchTriggered")) marks.push(mark("watch", item));
    else if (is(item, "memory")) marks.push(mark("memory", item));
    else if (
      is(item, "deliveryFailed") ||
      (is(item, "taskEnded") && (item.tone === "warning" || item.outcome?.ok === false))
    )
      marks.push(mark("problem", item));
  }
  return marks;
}

/** A line the agent says about what it attends to: a message id of home.ftl and its arguments. */
export interface Line {
  id: string;
  args: Record<string, string | number>;
}

const RECENT_MS = 10 * 60_000;

/**
 * What the agent says, in its own words: about the latest event when it is recent, else about what
 * it is busy with, what needs a person, or the quiet.
 */
export function lineOf(
  latest: JournalItem | null,
  state: AgentState,
  context: { tasks: readonly Task[]; troubled: number; quietUntil: string | null },
  now = Date.now(),
): Line {
  const people = (i: JournalItem) => i.people.map((p) => p.name).join(", ");
  if (latest && now - new Date(latest.at).getTime() < RECENT_MS) {
    const where = latest.room ?? latest.channels[0] ?? "";
    if (is(latest, "delivered") && latest.people.length)
      return { id: "home-say-delivered", args: { people: people(latest), where } };
    if (is(latest, "userTurn") && latest.people.length)
      return { id: "home-say-listening", args: { people: people(latest), where } };
    if (is(latest, "answer") && latest.people.length)
      return { id: "home-say-answering", args: { people: people(latest) } };
    if (is(latest, "toolCalled") && latest.tool) return { id: "home-say-tool", args: { tool: latest.tool } };
    if (is(latest, "presence") && latest.people.length)
      return latest.room
        ? { id: "home-say-presence-room", args: { people: people(latest), room: latest.room } }
        : { id: "home-say-presence-away", args: { people: people(latest) } };
    if (is(latest, "memory")) return { id: "home-say-memory", args: { people: people(latest) || "—" } };
  }
  const task = context.tasks[0];
  if (state === "working" && task)
    return {
      id: "home-say-working",
      args: { objective: task.objective, count: context.tasks.length, others: context.tasks.length - 1 },
    };
  if (context.troubled) return { id: "home-say-concerned", args: { count: context.troubled } };
  if (state === "sleeping" && context.quietUntil)
    return { id: "home-say-sleeping", args: { until: context.quietUntil } };
  return { id: "home-say-idle", args: {} };
}
