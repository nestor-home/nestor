import { useSuspenseQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { type Me, meQuery, type Scope } from "@/api";

/** What a screen may show or do: the server's finer scopes, grouped as reading or changing a part of the admin. */
export type Permission =
  | "journal:read"
  | "connections:read"
  | "connections:write"
  | "satellites:read"
  | "satellites:write"
  | "system:read"
  | "tasks:read"
  | "tasks:write"
  | "watches:read"
  | "watches:write"
  | "memories:read"
  | "memories:write"
  | "people:read"
  | "accounts:read"
  | "accounts:write"
  | "config:manage"
  | "agent:read";

/** Every scope the server grants, by name: a new one fails the typecheck here until it is placed. */
const PERMISSIONS: Record<Scope, Permission[]> = {
  "accounts.manage": ["accounts:read", "accounts:write"],
  "accounts.owners.manage": ["accounts:read", "accounts:write"],
  "household.read": ["people:read", "connections:read", "tasks:read", "watches:read", "memories:read"],
  "household.connections.manage": ["connections:read", "connections:write"],
  "own.connections.manage": ["connections:read", "connections:write"],
  "satellites.manage": ["satellites:read", "satellites:write"],
  "system.read": ["system:read", "satellites:read"],
  "journal.read.all": ["journal:read"],
  "journal.read.own": ["journal:read"],
  "memory.manage.all": ["memories:read", "memories:write"],
  "memory.manage.own": ["memories:read", "memories:write"],
  "tasks.manage": ["tasks:read", "tasks:write"],
  "tasks.manage.own": ["tasks:read", "tasks:write"],
  "watches.manage.all": ["watches:read", "watches:write"],
  "watches.manage.own": ["watches:read", "watches:write"],
  "config.manage": ["config:manage"],
  "agent.read": ["agent:read"],
};

export function permissions(scopes: readonly Scope[]): Permission[] {
  return [...new Set(scopes.flatMap((s) => PERMISSIONS[s]))];
}

/** The signed-in account. Only used below the `_app` layout, which loads it before rendering. */
export function useMe(): Me {
  return useSuspenseQuery(meQuery).data;
}

export function can(me: Pick<Me, "scopes">, permission: Permission): boolean {
  return permissions(me.scopes).includes(permission);
}

export function useCan(permission: Permission): boolean {
  return can(useMe(), permission);
}

/** Renders its children only when the account holds `scope`: the server refuses anyway, the UI does not tempt. */
export function Can({
  scope,
  children,
  otherwise = null,
}: {
  scope: Permission;
  children: ReactNode;
  otherwise?: ReactNode;
}) {
  return useCan(scope) ? children : otherwise;
}
