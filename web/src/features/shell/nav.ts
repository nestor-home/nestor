import type { LucideIcon } from "lucide-react";
import type { Scope } from "@/api";
import { SECTION_ICON } from "@/lib/icons";

export type SectionPath = keyof typeof SECTION_ICON;

export interface NavItem {
  to: SectionPath;
  label: string; // a message id of shell.ftl
  scope: Scope;
  key: string; // `g` then this key
  icon: LucideIcon;
}

export interface NavGroup {
  label: string | null; // a message id of shell.ftl
  items: NavItem[];
}

const item = (to: SectionPath, label: string, scope: Scope, key: string): NavItem => ({
  to,
  label,
  scope,
  key,
  icon: SECTION_ICON[to],
});

/** The information architecture: what happens, the household, and what is plugged in. */
export const NAV: NavGroup[] = [
  {
    label: null,
    items: [item("/", "nav-today", "journal:read", "h"), item("/journal", "nav-journal", "journal:read", "j")],
  },
  {
    label: "nav-group-household",
    items: [
      item("/people", "nav-people", "people:read", "p"),
      item("/memories", "nav-memories", "memories:read", "m"),
      item("/watches", "nav-watches", "watches:read", "v"),
      item("/tasks", "nav-tasks", "tasks:read", "t"),
    ],
  },
  {
    label: "nav-group-installation",
    items: [
      item("/connections", "nav-connections", "connections:read", "c"),
      item("/satellites", "nav-satellites", "satellites:read", "s"),
      item("/system", "nav-system", "satellites:read", "y"),
      item("/accounts", "nav-accounts", "accounts:read", "a"),
      item("/config", "nav-config", "config:manage", "f"),
    ],
  },
];

export function visibleNav(scopes: readonly Scope[]): NavGroup[] {
  return NAV.map((g) => ({ ...g, items: g.items.filter((i) => scopes.includes(i.scope)) })).filter(
    (g) => g.items.length,
  );
}

export function flatNav(scopes: readonly Scope[]): NavItem[] {
  return visibleNav(scopes).flatMap((g) => g.items);
}
