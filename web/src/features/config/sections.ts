/**
 * The Configuration area's pages: one per section or slot of the file, grouped as a person thinks
 * of them (who the agent is, what it is made of, the instance), then the vault and the history.
 */
import type { LucideIcon } from "lucide-react";
import {
  Bot,
  Brain,
  Cable,
  Download,
  History,
  House,
  KeyRound,
  MessageCircle,
  MessagesSquare,
  Plug,
  Radar,
  Server,
  SlidersHorizontal,
  Sparkles,
  Users,
  Workflow,
  Wrench,
} from "lucide-react";
import type { ConfigSchema } from "@/api";

export type PageKind = "section" | "household" | "slots" | "secrets" | "history";

export interface ConfigPage {
  slug: string;
  kind: PageKind;
  /** The document keys the page edits (problems and changes under them are counted here). */
  keys: string[];
  icon: LucideIcon;
  group: "agent" | "parts" | "instance" | "vault";
  /** A message id when the schema has no title for it. */
  label?: string;
}

export const PAGES: ConfigPage[] = [
  { slug: "persona", kind: "section", keys: ["persona"], icon: Bot, group: "agent" },
  { slug: "household", kind: "household", keys: ["household"], icon: Users, group: "agent" },
  { slug: "conversation", kind: "section", keys: ["conversation"], icon: MessageCircle, group: "agent" },
  { slug: "initiative", kind: "section", keys: ["initiative"], icon: Sparkles, group: "agent" },
  { slug: "model", kind: "slots", keys: ["model", "triage_model"], icon: Brain, group: "parts" },
  { slug: "channels", kind: "slots", keys: ["channels"], icon: MessagesSquare, group: "parts" },
  { slug: "executors", kind: "slots", keys: ["executors"], icon: Workflow, group: "parts" },
  { slug: "tools", kind: "slots", keys: ["tools"], icon: Wrench, group: "parts" },
  { slug: "inbound", kind: "slots", keys: ["inbound"], icon: Download, group: "parts" },
  { slug: "presence", kind: "slots", keys: ["presence"], icon: House, group: "parts" },
  { slug: "connectors", kind: "slots", keys: ["connectors"], icon: Plug, group: "parts" },
  { slug: "admin", kind: "section", keys: ["admin", "data_dir"], icon: Server, group: "instance" },
  { slug: "secrets", kind: "secrets", keys: [], icon: KeyRound, group: "vault", label: "cfg-secrets" },
  { slug: "history", kind: "history", keys: [], icon: History, group: "vault", label: "cfg-history" },
];

export const GROUP_LABEL: Record<ConfigPage["group"], string> = {
  agent: "cfg-group-agent",
  parts: "cfg-group-parts",
  instance: "cfg-group-instance",
  vault: "cfg-group-vault",
};

/**
 * The pages for this instance's schema: the known ones it has, then a page for any section or slot
 * the schema adds (a plugin's, a newer Nestor's), so nothing in the file is out of reach.
 */
export function pagesFor(schema: ConfigSchema): ConfigPage[] {
  const known = new Set(PAGES.flatMap((p) => p.keys));
  const has = (p: ConfigPage) => !p.keys.length || p.keys.some((k) => k in schema.sections || k in schema.slots);
  const added = (keys: string[], kind: PageKind, group: ConfigPage["group"]): ConfigPage[] =>
    keys.filter((k) => !known.has(k)).map((k) => ({ slug: k, kind, keys: [k], icon: SlidersHorizontal, group }));
  const extra = [
    ...added(Object.keys(schema.sections), "section", "agent"),
    ...added(Object.keys(schema.slots), "slots", "parts"),
  ];
  const pages = PAGES.filter(has);
  const vault = pages.findIndex((p) => p.group === "instance");
  return [...pages.slice(0, vault), ...extra, ...pages.slice(vault)];
}

export const pageOf = (slug: string, schema: ConfigSchema): ConfigPage | undefined =>
  pagesFor(schema).find((p) => p.slug === slug);

/** The page that edits a document key. */
export const pageOfKey = (key: string, schema: ConfigSchema): ConfigPage | undefined =>
  pagesFor(schema).find((p) => p.keys.includes(key));

/** A page's title in the reader's language: the schema's own, else the admin's catalogue. */
export function pageTitle(page: ConfigPage, schema: ConfigSchema, t: (id: string) => string): string {
  if (page.label) return t(page.label);
  const key = page.keys[0] ?? page.slug;
  return schema.section_titles[key] ?? schema.slots[key]?.title ?? key;
}

/** Icons for the families of components (the sheet that adds one). */
export const FAMILY_ICON: Record<string, LucideIcon> = {
  model: Brain,
  channel: MessagesSquare,
  executor: Workflow,
  tools: Wrench,
  inbound: Radar,
  presence: House,
  connector: Cable,
};
