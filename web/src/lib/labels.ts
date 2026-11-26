/** Values the server sends, as people read them: the server's own select messages, keyed by the value. */
import type {
  AuthKind,
  ConnectionStatus,
  Day,
  Frequency,
  Granularity,
  Kind,
  ModelType,
  Ring,
  Risk,
  Role,
  TaskState,
  TurnStatus,
} from "@/api";
import { tr } from "@/i18n/runtime";

const ROLE_HINT: Record<Role, string> = {
  owner: "role-owner-hint",
  admin: "role-admin-hint",
  member: "role-member-hint",
  guest: "role-guest-hint",
};

export const roleLabel = (role: Role) => tr("role-name", { role });
export const roleHint = (role: Role) => tr(ROLE_HINT[role]);
export const connectionStatusLabel = (status: ConnectionStatus) => tr("connection-status", { status });
export const riskLabel = (risk: Risk) => tr("tool-risk", { risk });
export const authLabel = (auth: AuthKind) => tr("auth-kind", { auth });
export const taskStateLabel = (state: TaskState) => tr("task-state", { state });
export const turnStatusLabel = (status: TurnStatus) => tr("turn-status", { status });
export const kindLabel = (kind: Kind) => tr("journal-kind", { kind });
export const modelTypeLabel = (type: ModelType) => tr("model-type", { type });
export const modelTypeHint = (type: ModelType) => tr("model-type-help", { type });
export const weekdayLabel = (day: Day) => tr("weekday", { day });
export const frequencyLabel = (frequency: Frequency) => tr("alert-frequency", { frequency });
/** Why an alert rang, in words: its time came, an event arrived, an item matched. */
export const rangBecause = (ring: Pick<Ring, "cause" | "item_title" | "item_kind">) =>
  tr("alert-rang-because", { cause: ring.cause, item: ring.item_title ?? "", kind: ring.item_kind ?? "" });
export const granularityLabel = (granularity: Granularity) => tr("home-granularity", { granularity });

/** A device as people know it: the name it was given, else its id. */
export const deviceName = (device: { id: string; name?: string | null }) => device.name ?? device.id;
