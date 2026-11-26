/** The mock backend's state. In the browser it survives reloads (OAuth navigates away and back). */

import type {
  Account,
  Confirmation,
  Connection,
  Connector,
  Executors,
  Home,
  Invitation,
  JournalEvent,
  Memory,
  Messages,
  PairingMethodId,
  Satellite,
  Schedule,
  Service,
  SystemInfo,
  TaskThread,
  Tool,
  Updates,
  Voice,
  Watch,
} from "@/api";
import { chats, type MockChat } from "./chats";
import type { ConfigDb } from "./config";
import * as config from "./config";
import { day } from "./day";
import type { MockPending, MockPerson } from "./fixtures";
import * as fixtures from "./fixtures";
import { brought } from "./instance";
import { stress, stressed } from "./stress";

/** An addition as the mock server keeps it (the enrollment code in clear: it is the mock's). */
export interface MockAddition {
  id: string;
  method: PairingMethodId;
  name: string | null;
  room: string | null;
  capabilities: string[] | null;
  created_at: string;
  expires_at: string;
  status: "active" | "completed" | "cancelled" | "expired";
  device_id: string | null;
  code: string | null;
}

export interface Db {
  signedIn: string | null; // account id
  people: MockPerson[];
  accounts: Account[];
  invitations: Invitation[];
  journal: JournalEvent[]; // newest first
  connectors: Connector[];
  connections: Connection[];
  tools: Record<string, Tool[]>; // by connection id
  services: Record<string, Service[]>; // by connection id
  pairing: MockPending[];
  additions: MockAddition[];
  satellites: Satellite[];
  tasks: TaskThread[];
  watches: Watch[];
  inbound: string[]; // what the inbound sources of the file bring (feeds, pages, webhooks), beside the accounts'
  schedules: Schedule[];
  messages: Messages;
  confirmations: Confirmation[];
  home: Home | null;
  memories: Memory[];
  system: SystemInfo;
  executors: Executors;
  updates: Updates;
  config: ConfigDb;
  voices: Record<string, Omit<Voice, "manageable">>; // by person; absent: never recorded
  chats: MockChat[]; // the signed-in person's
}

/** Bumped when the shape changes; the stress fixture keeps its own copy. */
const KEY = () => (stressed() ? "nestor.mock.db.v23.stress" : "nestor.mock.db.v23");

export function fresh(): Db {
  const settings = config.fresh();
  const doc = settings.document;
  const connections = fixtures.connections();
  const satellites = fixtures.satellites();
  const tasks = fixtures.tasks();
  const system = fixtures.system(doc, { satellites, connections, tasks });
  const journal = day();
  const learnt = journal.find((e) => e.item.links.memory === "m-07")?.item.position ?? null;
  const memories = fixtures
    .memories()
    .map((m) => (m.learnt_event === fixtures.LEARNT ? { ...m, learnt_event: learnt } : m));
  const state: Db = {
    signedIn: "acc-mathis",
    people: fixtures.people(doc),
    accounts: fixtures.accounts(),
    invitations: fixtures.invitations(),
    journal,
    connectors: fixtures.connectors(doc),
    connections,
    tools: Object.fromEntries(connections.map((c) => [c.id, fixtures.tools(c.kind, c.brand)])),
    services: Object.fromEntries(connections.map((c) => [c.id, fixtures.services(c, connections)])),
    pairing: fixtures.pairing(),
    additions: [],
    satellites,
    tasks,
    watches: fixtures.watches(),
    inbound: brought(doc),
    schedules: fixtures.schedules(),
    messages: fixtures.messages(),
    confirmations: fixtures.confirmations(),
    home: fixtures.home(
      doc,
      system.components.find((c) => c.slot === "home"),
      satellites,
    ),
    memories,
    system,
    executors: fixtures.executors(doc),
    updates: fixtures.updates(),
    config: settings,
    voices: fixtures.voices(),
    chats: chats(),
  };
  if (stressed()) stress(state);
  return state;
}

export let db: Db = fresh();

export function reset(next: Db = fresh()): void {
  db = next;
}

export function load(): void {
  try {
    const saved = sessionStorage.getItem(KEY());
    if (saved) db = JSON.parse(saved) as Db;
  } catch {
    db = fresh();
  }
}

export function save(): void {
  try {
    sessionStorage.setItem(KEY(), JSON.stringify(db));
  } catch {
    // storage unavailable: the state lasts until the next reload
  }
}
