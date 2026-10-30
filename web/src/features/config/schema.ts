/**
 * Reading `/config/schema`: what control a property needs, its label, whether it is secret or
 * advanced, and the document paths the forms edit. Pure functions, tested on their own.
 */
import type { ConfigDocument, ConfigProblem, JsonSchema, SecretShown } from "@/api";

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
  const entries = Object.entries(object.properties ?? {}).filter(([name]) => name !== "kind");
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
