/** The mock backend's state. In the browser it survives reloads (OAuth navigates away and back). */
import type {
  Account,
  Connection,
  Connector,
  Invitation,
  JournalEvent,
  Memory,
  PairingRequest,
  Person,
  Satellite,
  SystemInfo,
  Task,
  Tool,
  Watch,
} from "@/api";
import { day } from "./day";
import * as fixtures from "./fixtures";

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
  satellites: Satellite[];
  tasks: Task[];
  watches: Watch[];
  memories: Memory[];
  system: SystemInfo;
}

const KEY = "nestor.mock.db.v5"; // bumped when the shape changes

export function fresh(): Db {
  const connections = fixtures.connections();
  const journal = day();
  const learnt = journal.find((e) => e.links.memory === "m-07")?.id ?? null;
  const memories = fixtures.memories().map((m) => (m.learnt_event === "LEARNT" ? { ...m, learnt_event: learnt } : m));
  return {
    signedIn: "acc-mathis",
    people: fixtures.people(),
    accounts: fixtures.accounts(),
    invitations: fixtures.invitations(),
    journal,
    connectors: fixtures.connectors(),
    connections,
    tools: Object.fromEntries(connections.map((c) => [c.id, fixtures.tools(c.kind)])),
    pairing: fixtures.pairing(),
    satellites: fixtures.satellites(),
    tasks: fixtures.tasks(),
    watches: fixtures.watches(),
    memories,
    system: fixtures.system(),
  };
}

export let db: Db = fresh();

export function reset(next: Db = fresh()): void {
  db = next;
}

export function load(): void {
  try {
    const saved = sessionStorage.getItem(KEY);
    if (saved) db = JSON.parse(saved) as Db;
  } catch {
    db = fresh();
  }
}

export function save(): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(db));
  } catch {
    // storage unavailable: the state lasts until the next reload
  }
}
