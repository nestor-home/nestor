import { useSuspenseQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { type Me, meQuery, type Scope } from "@/api";

/** The signed-in account. Only used below the `_app` layout, which loads it before rendering. */
export function useMe(): Me {
  return useSuspenseQuery(meQuery).data;
}

export function can(me: Pick<Me, "scopes">, scope: Scope): boolean {
  return me.scopes.includes(scope);
}

export function useCan(scope: Scope): boolean {
  return can(useMe(), scope);
}

/** Renders its children only when the account holds `scope`: the server refuses anyway, the UI does not tempt. */
export function Can({
  scope,
  children,
  otherwise = null,
}: {
  scope: Scope;
  children: ReactNode;
  otherwise?: ReactNode;
}) {
  return useCan(scope) ? children : otherwise;
}
