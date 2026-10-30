/** Enumerations as people read them: each value maps to a message of `common.ftl`. */
import type { AuthKind, ConnectionStatus, Risk, Role, TaskStatus } from "@/api";
import { tr } from "@/i18n/runtime";

const ROLE = { owner: "role-owner", admin: "role-admin", member: "role-member", guest: "role-guest" } as const;
const ROLE_HINT = {
  owner: "role-owner-hint",
  admin: "role-admin-hint",
  member: "role-member-hint",
  guest: "role-guest-hint",
} as const;
const CONNECTION = {
  connected: "connection-status-connected",
  needs_reauth: "connection-status-needs-reauth",
  error: "connection-status-error",
} as const;
const RISK = { read: "risk-read", write: "risk-write", sensitive: "risk-sensitive" } as const;
const AUTH = { oauth2: "auth-oauth2", secret: "auth-secret", none: "auth-none" } as const;
const TASK = {
  running: "task-status-running",
  completed: "task-status-completed",
  failed: "task-status-failed",
  cancelled: "task-status-cancelled",
} as const;

export const roleLabel = (role: Role) => tr(ROLE[role]);
export const roleHint = (role: Role) => tr(ROLE_HINT[role]);
export const connectionStatusLabel = (status: ConnectionStatus) => tr(CONNECTION[status]);
export const riskLabel = (risk: Risk) => tr(RISK[risk]);
export const authLabel = (auth: AuthKind) => tr(AUTH[auth]);
export const taskStatusLabel = (status: TaskStatus) => tr(TASK[status]);
