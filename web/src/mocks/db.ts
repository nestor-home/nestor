/** The mock backend's state. In the browser it survives reloads (OAuth navigates away and back). */

import type {
  Account,
  Connection,
  Connector,
  Invitation,
  JournalEvent,
  Memory,
  PairingMethodId,
  PairingRequest,
  Person,
  Satellite,
  SystemInfo,
  Task,
  Tool,
  Watch,
} from "@/api";
import type { ConfigDb } from "./config";
import * as config from "./config";
import { day } from "./day";
import * as fixtures from "./fixtures";
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
  people: Person[];
  accounts: Account[];
  invitations: Invitation[];
  journal: JournalEvent[]; // newest first, with raw records
  connectors: Connector[];
  connections: Connection[];
  tools: Record<string, Tool[]>; // by connection id
  pairing: PairingRequest[];
  additions: MockAddition[];
  satellites: Satellite[];
  tasks: Task[];
  watches: Watch[];
  memories: Memory[];
  system: SystemInfo;
  config: ConfigDb;
}

/** Bumped when the shape changes; the stress fixture keeps its own copy. */
const KEY = () => (stressed() ? "nestor.mock.db.v7.stress" : "nestor.mock.db.v7");

export function fresh(): Db {
  const connections = fixtures.connections();
  const journal = day();
  const learnt = journal.find((e) => e.links.memory === "m-07")?.id ?? null;
  const memories = fixtures.memories().map((m) => (m.learnt_event === "LEARNT" ? { ...m, learnt_event: learnt } : m));
  const state: Db = {
    signedIn: "acc-mathis",
    people: fixtures.people(),
    accounts: fixtures.accounts(),
    invitations: fixtures.invitations(),
    journal,
    connectors: fixtures.connectors(),
    connections,
    tools: Object.fromEntries(connections.map((c) => [c.id, fixtures.tools(c.kind)])),
    pairing: fixtures.pairing(),
    additions: [],
    satellites: fixtures.satellites(),
    tasks: fixtures.tasks(),
    watches: fixtures.watches(),
    memories,
    system: fixtures.system(),
    config: config.fresh(),
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
