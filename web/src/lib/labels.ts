/** Values the server sends, as people read them: the server's own select messages, keyed by the value. */
import type { AuthKind, ConnectionStatus, Day, Granularity, Kind, ModelType, Risk, Role, TaskStatus } from "@/api";
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
export const taskStatusLabel = (status: TaskStatus) => tr("task-status", { status });
export const kindLabel = (kind: Kind) => tr("journal-kind", { kind });
export const modelTypeLabel = (type: ModelType) => tr("model-type", { type });
export const modelTypeHint = (type: ModelType) => tr("model-type-help", { type });
export const dayLabel = (day: Day) => tr("schedule-day", { day });
export const granularityLabel = (granularity: Granularity) => tr("home-granularity", { granularity });
