/**
 * What the file holds, in words a person reads: a setting's value (a secret is never shown), the
 * components of a slot with the mark each goes by, and one line saying where a page stands.
 */
import type { ConfigDocument } from "@/api";
import { tr } from "@/i18n/runtime";
import { kindName } from "@/lib/brands";
import {
  defaultText,
  fieldsOf,
  isRecord,
  isReference,
  isSecret,
  isShown,
  type JsonSchema,
  pluginOf,
  providerOf,
  resolve,
  type Schemas,
  type Slot,
  titleOf,
} from "./schema";
import type { ConfigPage } from "./sections";

/**
 * What a component's mark shows: the provider one of its fields names, as the runtime itself brands it
 * (`x-nestor.brands`: a host suffix for an address, `base_url`; a value for a name, a catalogue
 * model), else its kind.
 */
export function markOf(kind: string, entry: Record<string, unknown>, schema: unknown): string {
  const fields = isRecord(schema) && isRecord(schema.properties) ? Object.entries(schema.properties) : [];
  for (const [name, field] of fields) {
    const brands = isRecord(field) && isRecord(field["x-nestor"]) ? field["x-nestor"].brands : undefined;
    const value = entry[name];
    if (!isRecord(brands) || typeof value !== "string") continue;
    const host = URL.canParse(value) ? new URL(value).hostname : null;
    const found = Object.entries(brands).find(([key]) =>
      host === null ? key === value : host === key || host.endsWith(`.${key}`),
    );
    if (typeof found?.[1] === "string") return found[1];
  }
  return kind;
}

/** A component as a slot holds it: where it is in the document, what it is called, which plugin runs it. */
export interface Component {
  /** Its step under the slot's key: a name, an index, or none when the slot takes one. */
  at: string | number | null;
  name: string;
  plugin: string;
  provider: string;
  mark: string;
  entry: Record<string, unknown>;
}

/** The components of a slot in a document, in the file's order. */
export function componentsOf(slot: Slot, key: string, doc: ConfigDocument): Component[] {
  const value = doc[key];
  const one = (entry: Record<string, unknown>, at: Component["at"], name?: string): Component => {
    const plugin = pluginOf(slot, entry);
    const provider = providerOf(slot, plugin);
    return {
      at,
      name: name ?? String(entry.name || kindName(provider)),
      plugin,
      provider,
      mark: markOf(provider, entry, slot.kinds[plugin]),
      entry,
    };
  };
  if (slot.shape === "named")
    return isRecord(value) ? Object.entries(value).flatMap(([n, e]) => (isRecord(e) ? [one(e, n, n)] : [])) : [];
  if (slot.shape === "list")
    return Array.isArray(value) ? value.flatMap((e, i) => (isRecord(e) ? [one(e, i)] : [])) : [];
  return isRecord(value) ? [one(value, null)] : [];
}

/** A setting's value as a person reads it, or `null` when the file leaves it out. A secret is never shown. */
export function valueText(node: JsonSchema, value: unknown): string | null {
  if (value === undefined || value === null || value === "") return null;
  if (isSecret(node)) {
    if (isShown(value))
      return value.set ? tr("cfg-secret-set", { preview: value.preview ?? "•••" }) : tr("cfg-secret-unset");
    if (isReference(value)) return tr("cfg-secret-reference", { reference: value });
    return tr("cfg-secret-typed");
  }
  if (typeof value === "boolean") return tr(value ? "cfg-on" : "cfg-off");
  if (Array.isArray(value)) {
    if (!value.length) return null;
    return value.every((v) => typeof v !== "object") ? value.join(", ") : tr("cfg-entries", { count: value.length });
  }
  if (isRecord(value)) {
    const count = Object.keys(value).length;
    return count ? tr("cfg-entries", { count }) : null;
  }
  return String(value);
}

/** What applies when a setting is left out, as a person reads it. */
export function defaultShown(node: JsonSchema, root: JsonSchema): string | null {
  const value = resolve(node, root).schema.default ?? node.default;
  if (typeof value === "boolean") return tr(value ? "cfg-on" : "cfg-off");
  return defaultText(node, root);
}

const SHORT = 40;

/** A section in one line: its first short values, as written. */
function sectionLine(section: JsonSchema, value: unknown): string {
  const object = resolve(section, section).schema;
  const held = isRecord(value) ? value : {};
  return fieldsOf(object)
    .plain.filter(([, node]) => !isSecret(node))
    .map(([name]) => held[name])
    .filter(
      (v): v is string | number => typeof v === "number" || (typeof v === "string" && v !== "" && v.length <= SHORT),
    )
    .slice(0, 3)
    .join(" · ");
}

/** The people of the household, as the document names them. */
export function peopleOf(doc: ConfigDocument): Record<string, unknown>[] {
  return Array.isArray(doc.household) ? doc.household.filter(isRecord) : [];
}

/** A page of the file at a glance: the marks of what it holds, and one line saying what is set now. */
export function glanceOf(page: ConfigPage, schema: Schemas, doc: ConfigDocument): { marks: string[]; line: string } {
  if (page.kind === "household") return { marks: [], line: tr("cfg-sum-people", { count: peopleOf(doc).length }) };
  const slots = page.keys.flatMap((key) => {
    const slot = schema.slots[key];
    return slot ? [{ slot, components: componentsOf(slot, key, doc) }] : [];
  });
  if (slots.length) {
    const components = slots.flatMap((s) => s.components);
    if (!components.length)
      return { marks: [], line: tr(slots.some((s) => s.slot.required) ? "cfg-sum-needed" : "cfg-sum-none") };
    const names = components.map((c) => c.name);
    return {
      marks: [...new Set(components.map((c) => c.mark))],
      line:
        names.length > 4
          ? tr("cfg-sum-more", { names: names.slice(0, 3).join(", "), count: names.length - 3 })
          : names.join(", "),
    };
  }
  const line = page.keys
    .map((key) => {
      const section = schema.sections[key];
      // `data_dir` is a top-level value: its schema wraps it as the one property of an object
      return section ? sectionLine(section, key === "data_dir" ? doc : doc[key]) : "";
    })
    .find(Boolean);
  return { marks: [], line: line ?? tr("cfg-sum-defaults") };
}

/** The settings that name a component of a named slot (the roles a model serves), by their titles. */
export function rolesOf(schema: Schemas, doc: ConfigDocument, slot: string, name: string): string[] {
  return Object.entries(schema.sections).flatMap(([key, section]) => {
    const held = doc[key];
    if (!isRecord(held)) return [];
    return Object.entries(resolve(section, section).schema.properties ?? {})
      .filter(([field, node]) => node["x-nestor"]?.reference === slot && held[field] === name)
      .map(([field, node]) => titleOf(node, field));
  });
}
