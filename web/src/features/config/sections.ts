/**
 * The Configuration area's pages: one per section or slot of the file, grouped by what a person
 * tunes (the agent, the household, how it talks and listens, what it can reach, the installation).
 */
import type { LucideIcon } from "lucide-react";
import {
  AudioLines,
  BookMarked,
  Bot,
  Brain,
  CircleArrowUp,
  Download,
  History,
  House,
  KeyRound,
  MessagesSquare,
  Plug,
  Server,
  SlidersHorizontal,
  Sparkles,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";
import type { Schemas } from "./schema";

type PageKind = "section" | "household" | "slots" | "secrets" | "history";

export const GROUPS = ["agent", "household", "talk", "reach", "install"] as const;
export type Group = (typeof GROUPS)[number];

export interface ConfigPage {
  slug: string;
  kind: PageKind;
  /** The document keys the page edits (problems and changes under them are counted here). */
  keys: string[];
  icon: LucideIcon;
  group: Group;
  /** A message id when the schema has no title for it. */
  label?: string;
  /** A message id: what the page tunes, in one sentence. */
  about?: string;
}

const PAGES: ConfigPage[] = [
  { slug: "persona", kind: "section", keys: ["persona"], icon: Bot, group: "agent", about: "cfg-about-persona" },
  {
    slug: "initiative",
    kind: "section",
    keys: ["initiative"],
    icon: Sparkles,
    group: "agent",
    about: "cfg-about-initiative",
  },
  { slug: "memory", kind: "section", keys: ["memory"], icon: BookMarked, group: "agent", about: "cfg-about-memory" },
  {
    slug: "household",
    kind: "household",
    keys: ["household"],
    icon: Users,
    group: "household",
    about: "cfg-about-household",
  },
  {
    slug: "voices",
    kind: "section",
    keys: ["voices"],
    icon: AudioLines,
    group: "household",
    about: "cfg-about-voices",
  },
  {
    slug: "models",
    kind: "slots",
    keys: ["models", "agent", "alerts"],
    icon: Brain,
    group: "talk",
    about: "cfg-about-models",
  },
  {
    slug: "channels",
    kind: "slots",
    keys: ["channels"],
    icon: MessagesSquare,
    group: "talk",
    about: "cfg-about-channels",
  },
  { slug: "home", kind: "slots", keys: ["home"], icon: House, group: "reach", about: "cfg-about-home" },
  {
    slug: "connectors",
    kind: "slots",
    keys: ["connectors"],
    icon: Plug,
    group: "reach",
    about: "cfg-about-connectors",
  },
  { slug: "tools", kind: "slots", keys: ["tools"], icon: Wrench, group: "reach", about: "cfg-about-tools" },
  { slug: "inbound", kind: "slots", keys: ["inbound"], icon: Download, group: "reach", about: "cfg-about-inbound" },
  {
    slug: "executors",
    kind: "slots",
    keys: ["executors"],
    icon: Workflow,
    group: "reach",
    about: "cfg-about-executors",
  },
  {
    slug: "admin",
    kind: "section",
    keys: ["admin", "data_dir"],
    icon: Server,
    group: "install",
    about: "cfg-about-admin",
  },
  {
    slug: "updates",
    kind: "section",
    keys: ["updates"],
    icon: CircleArrowUp,
    group: "install",
    about: "cfg-about-updates",
  },
  {
    slug: "secrets",
    kind: "secrets",
    keys: [],
    icon: KeyRound,
    group: "install",
    label: "cfg-secrets",
    about: "cfg-secrets-intro",
  },
  {
    slug: "history",
    kind: "history",
    keys: [],
    icon: History,
    group: "install",
    label: "cfg-history",
    about: "cfg-history-intro",
  },
];

export const GROUP_LABEL: Record<Group, string> = {
  agent: "cfg-group-agent",
  household: "cfg-group-household",
  talk: "cfg-group-talk",
  reach: "cfg-group-reach",
  install: "cfg-group-install",
};

/**
 * The pages for this instance's schema: the known ones it has, then a page for any section or slot
 * the schema adds (a plugin's, a newer Nestor's), so nothing in the file is out of reach.
 */
function pagesFor(schema: Schemas): ConfigPage[] {
  const known = new Set(PAGES.flatMap((p) => p.keys));
  const has = (p: ConfigPage) => !p.keys.length || p.keys.some((k) => k in schema.sections || k in schema.slots);
  const added = (keys: string[], kind: PageKind, group: Group): ConfigPage[] =>
    keys.filter((k) => !known.has(k)).map((k) => ({ slug: k, kind, keys: [k], icon: SlidersHorizontal, group }));
  return [
    ...PAGES.filter(has),
    ...added(Object.keys(schema.sections), "section", "agent"),
    ...added(Object.keys(schema.slots), "slots", "reach"),
  ];
}

/** The pages by group, in the order a person meets them; a group without a page is left out. */
export function groupsFor(schema: Schemas): { group: Group; pages: ConfigPage[] }[] {
  const pages = pagesFor(schema);
  return GROUPS.map((group) => ({ group, pages: pages.filter((p) => p.group === group) })).filter(
    (g) => g.pages.length,
  );
}

export const pageOf = (slug: string, schema: Schemas): ConfigPage | undefined =>
  pagesFor(schema).find((p) => p.slug === slug);

/** The page that edits a document key. */
export const pageOfKey = (key: string, schema: Schemas): ConfigPage | undefined =>
  pagesFor(schema).find((p) => p.keys.includes(key));

/** A page's title in the reader's language: the schema's own, else the admin's catalogue. */
export function pageTitle(page: ConfigPage, schema: Schemas, t: (id: string) => string): string {
  if (page.label) return t(page.label);
  const key = page.keys[0] ?? page.slug;
  return schema.section_titles[key] ?? schema.slots[key]?.title ?? key;
}
