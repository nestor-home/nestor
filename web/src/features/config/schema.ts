/**
 * Reading `/config/schema`: what control a property needs, its label, whether it is secret or
 * advanced, and the document paths the forms edit. Pure functions, tested on their own.
 */
import type { ConfigDocument, ConfigProblem, ConfigSchema, ConfigSlot, ModelType, Suggest } from "@/api";

/** A JSON Schema as `/config/schema` sends it, with Nestor's `x-nestor` annotations. */
export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  additionalProperties?: boolean | JsonSchema;
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  enum?: (string | number)[];
  const?: unknown;
  default?: unknown;
  format?: string;
  writeOnly?: boolean;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  minLength?: number;
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  "x-nestor"?: {
    field?: string;
    title?: string;
    help?: string | null;
    secret?: boolean;
    /** a map whose values are secrets (MCP headers): each value is kept or replaced on its own */
    secret_values?: boolean;
    advanced?: boolean;
    group?: string;
    /** the named slot (`models`) whose names the property takes */
    reference?: string | null;
    /** the type of model the reference takes: only those are offered */
    model_type?: ModelType | null;
    /** what a map's keys and values are picked from: the household's people, the home system's residents */
    suggest_keys?: Suggest | null;
    suggest_values?: Suggest | null;
  };
}

/**
 * `/config/schema` read as what it is: JSON Schemas (sent as free JSON) with Nestor's `x-nestor`
 * annotations, by section and by plugin kind.
 */
export interface Schemas extends Omit<ConfigSchema, "sections" | "slots"> {
  sections: Record<string, JsonSchema>;
  slots: Record<string, Slot>;
}

/** A slot of components, with the settings of each plugin as JSON Schema, by plugin id. */
export type Slot = Omit<ConfigSlot, "kinds"> & { kinds: Record<string, JsonSchema> };

/** The id of the plugin an entry picks (its key in `slot.kinds`): its `kind`, or a model's provider and type. */
export const pluginOf = (slot: Slot, entry: Record<string, unknown>): string =>
  slot.picks.map((key) => String(entry[key] ?? "")).join("-");

/** A new entry for a plugin: the values that pick it, as its schema fixes them. */
export function entryOf(slot: Slot, plugin: string): Record<string, unknown> {
  const properties = slot.kinds[plugin]?.properties ?? {};
  return Object.fromEntries(slot.picks.map((key) => [key, properties[key]?.const]));
}

/** What people know a plugin by: its kind, or a model's provider (`elevenlabs`). */
export const providerOf = (slot: Slot, plugin: string): string => {
  const value = entryOf(slot, plugin)[slot.picks[0] ?? "kind"];
  return typeof value === "string" ? value : plugin;
};

/** A secret as the configuration shows it: never its value. */
export interface SecretShown {
  set: boolean;
  preview: string | null;
}

export type Path = (string | number)[];

/** The document as a form holds it: anything JSON. */
export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

export const keyOf = (path: Path): string => path.join(".");

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

// -- paths ---------------------------------------------------------------------------------------

export function getAt(node: unknown, path: Path): unknown {
  let at: unknown = node;
  for (const step of path) {
    if (Array.isArray(at)) at = at[Number(step)];
    else if (isRecord(at)) at = at[String(step)];
    else return undefined;
  }
  return at;
}

/** A copy of `node` with `value` at `path`; `undefined` removes the key (the default applies). */
export function setAt<T>(node: T, path: Path, value: unknown): T {
  if (!path.length) return value as T;
  const [step, ...rest] = path as [string | number, ...Path];
  if (Array.isArray(node)) {
    const copy = [...node];
    const index = Number(step);
    if (value === undefined && !rest.length) copy.splice(index, 1);
    else copy[index] = setAt(copy[index], rest, value);
    return copy as T;
  }
  const base: Record<string, unknown> = isRecord(node) ? { ...node } : {};
  const key = String(step);
  const next = rest.length ? setAt(base[key], rest, value) : value;
  if (next === undefined) delete base[key];
  else base[key] = next;
  return base as T;
}

/** Moves the item of a list one place up (-1) or down (+1). */
export function move<T>(list: T[], index: number, by: -1 | 1): T[] {
  const to = index + by;
  if (to < 0 || to >= list.length) return list;
  const copy = [...list];
  const [item] = copy.splice(index, 1);
  if (item !== undefined) copy.splice(to, 0, item);
  return copy;
}

// -- schemas -------------------------------------------------------------------------------------

/** A property with its `$ref` followed (its own annotations win) and `anyOf […, null]` unwrapped. */
export interface Resolved {
  schema: JsonSchema;
  nullable: boolean;
}

export function deref(node: JsonSchema, root: JsonSchema): JsonSchema {
  if (!node.$ref) return node;
  const name = node.$ref.split("/").at(-1) ?? "";
  const { $ref: _ref, ...own } = node;
  return { ...(root.$defs?.[name] ?? {}), ...own };
}

export function resolve(node: JsonSchema, root: JsonSchema): Resolved {
  const schema = deref(node, root);
  if (!schema.anyOf) return { schema, nullable: false };
  const options = schema.anyOf.map((o) => deref(o, root));
  const real = options.filter((o) => o.type !== "null");
  const nullable = real.length < options.length;
  if (real.length !== 1 || !real[0]) return { schema, nullable };
  const { anyOf: _anyOf, ...own } = schema;
  return { schema: { ...real[0], ...own }, nullable };
}

export function isSecret(node: JsonSchema): boolean {
  return Boolean(
    node["x-nestor"]?.secret ||
      node.format === "password" ||
      node.writeOnly === true ||
      node.anyOf?.some((o) => o.format === "password" || o.writeOnly === true),
  );
}

export type Control =
  | "secret"
  | "text"
  | "long-text"
  | "path"
  | "enum"
  | "reference"
  | "boolean"
  | "integer"
  | "number"
  | "list"
  | "object"
  | "map"
  | "json"
  | "const";

const LONG = new Set(["character", "description", "instructions", "style", "apology"]);

/** The control a property needs. */
export function controlOf(node: JsonSchema, root: JsonSchema, field = "", value?: unknown): Control {
  if (isSecret(node)) return "secret";
  if (node["x-nestor"]?.reference) return "reference";
  const { schema } = resolve(node, root);
  if (schema.const !== undefined) return "const";
  if (schema.enum) return "enum";
  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;
  if (type === "boolean") return "boolean";
  if (type === "integer") return "integer";
  if (type === "number") return "number";
  if (type === "array") return isRecord(schema.items) && !schema.items.properties ? "list" : "json";
  if (type === "object" || schema.properties || schema.additionalProperties) {
    if (schema.properties) return "object";
    if (isRecord(schema.additionalProperties)) return "map";
    return "json";
  }
  if (type === "string") {
    if (schema.format === "path") return "path";
    if (LONG.has(field) || (typeof value === "string" && (value.length > 90 || value.includes("\n"))))
      return "long-text";
    return "text";
  }
  return "json";
}

export const titleOf = (node: JsonSchema, field: string): string => node["x-nestor"]?.title ?? node.title ?? field;
export const helpOf = (node: JsonSchema): string | null => node["x-nestor"]?.help ?? null;
export const isAdvanced = (node: JsonSchema): boolean => Boolean(node["x-nestor"]?.advanced);

/** The properties a form shows, in schema order: the plain ones, then the advanced. */
export function fieldsOf(object: JsonSchema): { plain: [string, JsonSchema][]; advanced: [string, JsonSchema][] } {
  const entries = Object.entries(object.properties ?? {}).filter(([, p]) => p.const === undefined); // what picks the plugin
  return {
    plain: entries.filter(([, p]) => !isAdvanced(p)),
    advanced: entries.filter(([, p]) => isAdvanced(p)),
  };
}

/** The default a property shows as its placeholder, in words a person can read. */
export function defaultText(node: JsonSchema, root: JsonSchema): string | null {
  const value = resolve(node, root).schema.default ?? node.default;
  if (value === undefined || value === null || value === "") return null;
  if (Array.isArray(value)) return value.length ? value.join(", ") : null;
  if (isRecord(value)) return Object.keys(value).length ? JSON.stringify(value) : null;
  return String(value);
}

// -- named components ----------------------------------------------------------------------------

/** What a component of a named slot (`models`) may be called: as the configuration accepts it. */
export const NAME = /^[A-Za-z0-9][A-Za-z0-9_.-]*$/;

/** A name for a new component of a named slot: `base`, or `base-2`, `base-3`… when taken. */
export function freeName(base: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

/**
 * The document with a component of a named slot renamed in place (its order kept), and every
 * section setting that referred to it by name following.
 */
export function renamed(
  doc: ConfigDocument,
  sections: Record<string, JsonSchema>,
  slot: string,
  from: string,
  to: string,
): ConfigDocument {
  const named = isRecord(doc[slot]) ? (doc[slot] as Record<string, unknown>) : {};
  const next: ConfigDocument = {
    ...doc,
    [slot]: Object.fromEntries(Object.entries(named).map(([k, v]) => [k === from ? to : k, v])),
  };
  for (const [key, section] of Object.entries(sections)) {
    const value = next[key];
    if (!isRecord(value)) continue;
    const following = Object.entries(section.properties ?? {}).filter(
      ([field, node]) => node["x-nestor"]?.reference === slot && value[field] === from,
    );
    if (following.length) next[key] = { ...value, ...Object.fromEntries(following.map(([field]) => [field, to])) };
  }
  return next;
}

// -- secrets -------------------------------------------------------------------------------------

export const isShown = (value: unknown): value is SecretShown =>
  isRecord(value) && typeof value.set === "boolean" && !("value" in value);

export const isTyped = (value: unknown): value is { value: string } =>
  isRecord(value) && typeof value.value === "string";

export const isReference = (value: unknown): value is string => typeof value === "string" && /\$\{[^}]+\}/.test(value);

/** What a person typed into a secret field, as the API takes it: a reference stays a reference. */
export function typedSecret(text: string): unknown {
  const trimmed = text.trim();
  if (/^\$\{[^}]+\}$/.test(trimmed)) return trimmed;
  return { value: text };
}

// -- problems ------------------------------------------------------------------------------------

/** Problems by the dotted path they point at. */
export function problemsByPath(problems: readonly ConfigProblem[]): Map<string, ConfigProblem[]> {
  const out = new Map<string, ConfigProblem[]>();
  for (const p of problems) out.set(keyOf(p.path), [...(out.get(keyOf(p.path)) ?? []), p]);
  return out;
}

/** The problems at or under a path (a component's card, a section of the sub-navigation). */
export function problemsUnder(problems: readonly ConfigProblem[], path: Path): ConfigProblem[] {
  const prefix = keyOf(path);
  return problems.filter((p) => {
    const key = keyOf(p.path);
    return key === prefix || key.startsWith(`${prefix}.`);
  });
}

// -- changes -------------------------------------------------------------------------------------

/** The top-level keys whose value differs between two documents. */
export function changedKeys(before: ConfigDocument, after: ConfigDocument): Set<string> {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  return new Set([...keys].filter((k) => JSON.stringify(before[k]) !== JSON.stringify(after[k])));
}

/** A value of the diff as a line of text. */
export function shown(value: unknown): string {
  if (value === null || value === undefined) return "∅";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}
