import { useSuspenseQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { type Me, meQuery, type Scope } from "@/api";

/**
 * Every scope the server grants, by name, as what a screen may show or do: reading or changing a part
 * of the admin. A new scope fails the typecheck here until it is placed.
 */
const PERMISSIONS = {
  "accounts.manage": ["accounts:read", "accounts:write"],
  "accounts.owners.manage": ["accounts:read", "accounts:write"],
  "household.read": ["people:read", "home:read", "connections:read", "tasks:read", "watches:read", "memories:read"],
  "household.connections.manage": ["connections:read", "connections:write"],
  "own.connections.manage": ["connections:read", "connections:write"],
  "satellites.manage": ["satellites:read", "satellites:write"],
  "system.read": ["system:read", "satellites:read"],
  "journal.read.all": ["journal:read", "messages:read"],
  "journal.read.own": ["journal:read", "messages:read"],
  "memory.manage.all": ["memories:read", "memories:write"],
  "memory.manage.own": ["memories:read", "memories:write"],
  "tasks.manage": ["tasks:read", "tasks:write"],
  "tasks.manage.own": ["tasks:read", "tasks:write"],
  "watches.manage.all": ["watches:read", "watches:write"],
  "watches.manage.own": ["watches:read", "watches:write"],
  "schedules.manage.all": ["schedules:read", "schedules:write"],
  "schedules.manage.own": ["schedules:read", "schedules:write"],
  "config.manage": ["config:manage"],
  "agent.read": ["agent:read"],
} as const satisfies Record<Scope, readonly string[]>;

export type Permission = (typeof PERMISSIONS)[Scope][number];

/** Per list of scopes (one per `/me` answer): computed once, read on every render. */
const granted = new WeakMap<readonly Scope[], ReadonlySet<Permission>>();

export function permissions(scopes: readonly Scope[]): ReadonlySet<Permission> {
  let found = granted.get(scopes);
  if (!found) {
    found = new Set(scopes.flatMap((s) => PERMISSIONS[s]));
    granted.set(scopes, found);
  }
  return found;
}

/** The signed-in account. Only used below the `_app` layout, which loads it before rendering. */
export function useMe(): Me {
  return useSuspenseQuery(meQuery).data;
}

export function can(me: Pick<Me, "scopes">, permission: Permission): boolean {
  return permissions(me.scopes).has(permission);
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
