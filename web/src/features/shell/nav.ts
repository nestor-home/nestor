import type { LucideIcon } from "lucide-react";
import {
  BookMarked,
  House,
  KeyRound,
  ListChecks,
  MessageCircle,
  Plug,
  RadioTower,
  ScrollText,
  Server,
  Settings2,
  SlidersHorizontal,
  Sun,
} from "lucide-react";
import type { Scope } from "@/api";
import { type Permission, permissions } from "@/lib/session";

/** A place one goes to: its page, who may see it (holding one of `any`), and `g` then its key to jump there. */
export interface Destination {
  to:
    | "/"
    | "/chat"
    | "/activity"
    | "/house"
    | "/settings"
    | "/journal"
    | "/memories"
    | "/connections"
    | "/satellites"
    | "/accounts"
    | "/config"
    | "/system";
  label: string; // a message id of shell.ftl
  icon: LucideIcon;
  any: Permission[];
  key: string;
}

/** A space of the rail: one of the few places the household goes to, named by what one does there. It
 * holds the pages one reaches from it, so the rail still says where one is. */
export interface Space extends Destination {
  holds: Destination[]; // its own pages, listed in the palette
  covers: string[]; // every path that belongs to it
}

const JOURNAL: Destination = {
  to: "/journal",
  label: "nav-journal",
  icon: ScrollText,
  any: ["journal:read"],
  key: "j",
};
const MEMORIES: Destination = {
  to: "/memories",
  label: "nav-memories",
  icon: BookMarked,
  any: ["memories:read"],
  key: "m",
};
const INSTALLATION: Destination[] = [
  { to: "/connections", label: "nav-connections", icon: Plug, any: ["connections:read"], key: "c" },
  { to: "/satellites", label: "nav-satellites", icon: RadioTower, any: ["satellites:read"], key: "s" },
  { to: "/accounts", label: "nav-accounts", icon: KeyRound, any: ["accounts:read"], key: "a" },
  { to: "/config", label: "nav-config", icon: SlidersHorizontal, any: ["config:manage"], key: "f" },
  { to: "/system", label: "nav-system", icon: Server, any: ["system:read"], key: "y" },
];

export const SPACES: Space[] = [
  { to: "/", label: "space-today", icon: Sun, any: ["journal:read"], key: "h", holds: [JOURNAL], covers: ["/journal"] },
  { to: "/chat", label: "space-chat", icon: MessageCircle, any: ["chat:write"], key: "k", holds: [], covers: [] },
  {
    to: "/activity",
    label: "space-activity",
    icon: ListChecks,
    any: ["schedules:read", "watches:read", "tasks:read", "messages:read"],
    key: "e",
    holds: [],
    covers: ["/tasks", "/watches"],
  },
  {
    to: "/house",
    label: "space-house",
    icon: House,
    any: ["people:read"],
    key: "o",
    holds: [MEMORIES],
    covers: ["/people", "/memories"],
  },
];

export const SETTINGS: Space = {
  to: "/settings",
  label: "space-settings",
  icon: Settings2,
  any: INSTALLATION.flatMap((d) => d.any),
  key: "r",
  holds: INSTALLATION,
  covers: INSTALLATION.map((d) => d.to),
};

const allowed = (destination: Destination, scopes: readonly Scope[]) =>
  destination.any.some((p) => permissions(scopes).has(p));

export function visibleSpaces(scopes: readonly Scope[]): { spaces: Space[]; settings: Space | null } {
  return { spaces: SPACES.filter((s) => allowed(s, scopes)), settings: allowed(SETTINGS, scopes) ? SETTINGS : null };
}

/** Every place the account may jump to: the spaces, then the pages they hold. */
export function destinations(scopes: readonly Scope[]): Destination[] {
  const all = [...SPACES, SETTINGS];
  return [...all, ...all.flatMap((s) => s.holds)].filter((d) => allowed(d, scopes));
}

/** Whether `path` is in this space: its own page, or a page it covers. */
export function inSpace(space: Space, path: string): boolean {
  if (space.to === "/" && path === "/") return true;
  return [space.to, ...space.covers].some((p) => p !== "/" && (path === p || path.startsWith(`${p}/`)));
}
