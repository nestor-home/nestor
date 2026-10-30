/**
 * The configuration file as the mock server keeps it: the document as written (references stay
 * `${…}`), the vault of secrets, the history of earlier files, and the checks Nestor runs before
 * writing. The schemas are the ones a real instance answered (`config/schema.{fr,en}.json`).
 */
import type { ConfigDocument, ConfigProblem, JsonSchema } from "@/api";
import type { components } from "@/api/schema.gen";
import schemaEn from "./config/schema.en.json";
import schemaFr from "./config/schema.fr.json";
import { minutes } from "./fixtures";
import type { Lang } from "./messages";
import { render } from "./messages";

type S = components["schemas"];
type Change = S["ChangeOut"];

export const SCHEMAS: Record<Lang, S["ConfigSchemaOut"]> = {
  fr: schemaFr as S["ConfigSchemaOut"],
  en: schemaEn as S["ConfigSchemaOut"],
};

export interface VaultSecret {
  value: string;
  at: string;
}

export interface ConfigDb {
  document: ConfigDocument;
  path: string;
  restart_required: boolean;
  pending_changes: string[];
  history: { id: string; at: string; document: ConfigDocument }[];
  vault: Record<string, VaultSecret>;
}

const SLOTS = ["model", "triage_model", "channels", "executors", "tools", "inbound", "presence", "connectors"];

/** References as a configuration file writes them. */
const vault = (name: string) => `\${secret:${name}}`;
const environ = (name: string) => `\${${name}}`;

/** Richie's household, as its `richie.yaml` could read. */
export function document(): ConfigDocument {
  return {
    data_dir: "data/richie",
    persona: {
      name: "Richie",
      locale: "fr-FR",
      language: "French",
      timezone: "Europe/Paris",
      character:
        "Tu es Richie, l'assistant de la maison Lambert. Tu parles simplement, avec chaleur et un peu d'humour, et tu vas droit au but.",
    },
    household: [
      { id: "mathis", name: "Mathis", accounts: ["voice:*", "telegram:@mathis_l"], reach: "telegram:@mathis_l" },
      { id: "lea", name: "Léa", accounts: ["voice:*", "telegram:@lea_lambert"], reach: "voice" },
      { id: "jules", name: "Jules", accounts: ["voice:*"] },
      { id: "odile", name: "Odile", accounts: ["telegram:@odile.m"], reach: "telegram:@odile.m" },
    ],
    model: {
      kind: "openai-compatible",
      name: "sonnet",
      base_url: "https://openrouter.ai/api/v1",
      api_key: vault("model.api_key"),
      model: "anthropic/claude-sonnet-4.6",
      extra_body: { provider: { order: ["anthropic"] } },
    },
    triage_model: {
      kind: "openai-compatible",
      base_url: "https://openrouter.ai/api/v1",
      api_key: vault("model.api_key"),
      model: "anthropic/claude-haiku-4.5",
    },
    channels: [
      {
        kind: "voice",
        room: "salon",
        port: 7870,
        speech: { api_key: vault("channels.voice.speech.api_key"), voice_id: "Xb7hH8MSUJpSbSDYk0k2" },
      },
      { kind: "telegram", token: environ("TELEGRAM_TOKEN") },
    ],
    executors: [
      {
        kind: "hermes",
        base_url: "http://hermes.local:8642/v1",
        api_key: vault("executors.hermes.api_key"),
        model: "hermes-agent",
        description: "Recherches longues, code, et tout ce qui demande plusieurs étapes.",
      },
    ],
    tools: [
      {
        kind: "mcp",
        name: "maison",
        url: "http://homeassistant.local:8123/mcp_server/sse",
        transport: "sse",
        token: vault("tools.maison.token"),
        risks: { HassTurnOff: "write", HassLockUnlock: "sensitive" },
        headers: { "X-Household": "lambert-maison-7d2f" },
      },
    ],
    presence: {
      kind: "home-assistant",
      url: "http://homeassistant.local:8123",
      token: vault("presence.token"),
      people: { mathis: "person.mathis", lea: "person.lea" },
      rooms: { salon: "area.salon", cuisine: "area.cuisine" },
    },
    connectors: [{ kind: "google" }, { kind: "imap" }],
    initiative: { quiet_hours: "22:30-07:30", main_room: "salon" },
    admin: { host: "0.0.0.0", port: 8080, public_url: "https://nestor.lambert.family" },
  };
}

export function fresh(): ConfigDb {
  const now = document();
  const older = structuredClone(now) as Record<string, Record<string, unknown>>;
  (older.persona as Record<string, unknown>).character = "Tu es Richie, l'assistant de la maison Lambert.";
  (older.initiative as Record<string, unknown>).quiet_hours = "23:00-07:00";
  const oldest = structuredClone(older);
  delete (oldest as Record<string, unknown>).triage_model;
  return {
    document: now,
    path: "/home/mathis/richie-framework/configs/richie.yaml",
    restart_required: false,
    pending_changes: [],
    history: [
      { id: "20261029T183012120000Z", at: minutes(60 * 26), document: older },
      { id: "20261021T090455031000Z", at: minutes(60 * 24 * 9), document: oldest },
    ],
    vault: {
      "model.api_key": { value: "sk-or-v1-4f1c9a2b7d", at: minutes(60 * 24 * 30) },
      "channels.voice.speech.api_key": { value: "sk_e1d0a8c7b6f5", at: minutes(60 * 24 * 30) },
      "executors.hermes.api_key": { value: "hermes-7c0f2b91", at: minutes(60 * 24 * 12) },
      "tools.maison.token": { value: "eyJhbGciOiJIUzI1NiJ9.maison", at: minutes(60 * 24 * 12) },
      "presence.token": { value: "eyJhbGciOiJIUzI1NiJ9.presence", at: minutes(60 * 24 * 12) },
      "github.token": { value: "ghp_unused0000", at: minutes(60 * 24 * 40) },
    },
  };
}

// -- reading the schemas -------------------------------------------------------------------------

type Path = (string | number)[];

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

function resolve(node: JsonSchema, root: JsonSchema): JsonSchema {
  if (node.$ref) {
    const name = node.$ref.split("/").at(-1) ?? "";
    const { $ref: _, ...rest } = node;
    return { ...(root.$defs?.[name] ?? {}), ...rest };
  }
  return node;
}

function isSecret(node: JsonSchema): boolean {
  return node.format === "password" || node.writeOnly === true || Boolean(node.anyOf?.some((o) => isSecret(o)));
}

/** Every path of a document holding a secret, with the vault name a typed value goes under. */
export function secretsOf(doc: ConfigDocument): { path: Path; name: string }[] {
  const found: { path: Path; name: string }[] = [];
  const schema = SCHEMAS.fr;
  for (const key of SLOTS) {
    const slot = schema.slots[key];
    const value = doc[key];
    if (!slot || value === undefined || value === null) continue;
    const entries = slot.many && Array.isArray(value) ? value : [value];
    entries.forEach((entry, index) => {
      if (!isObject(entry)) return;
      const kind = slot.kinds[String(entry.kind)] as JsonSchema | undefined;
      if (!kind) return;
      const where: Path = slot.many ? [key, index] : [key];
      const label = slot.many ? [key, String(entry.name ?? entry.kind)] : [key];
      const walk = (node: JsonSchema, value: Record<string, unknown>, path: string[]) => {
        for (const [name, child] of Object.entries(node.properties ?? {})) {
          const resolved = resolve(child, kind);
          const map = value[name];
          if (resolved["x-nestor"]?.secret_values && isObject(map)) {
            // a map of secrets (MCP headers): each value is kept apart, under its own key
            for (const key of Object.keys(map)) {
              found.push({ path: [...where, ...path, name, key], name: [...label, ...path, name, key].join(".") });
            }
          } else if (isSecret(resolved) && value[name] !== undefined && value[name] !== null) {
            found.push({ path: [...where, ...path, name], name: [...label, ...path, name].join(".") });
          } else if (resolved.properties && isObject(value[name])) {
            walk(resolved, value[name] as Record<string, unknown>, [...path, name]);
          }
        }
      };
      walk(kind, entry, []);
    });
  }
  return found;
}

function get(node: unknown, path: Path): unknown {
  let at = node;
  for (const step of path) {
    if (Array.isArray(at)) at = at[Number(step)];
    else if (isObject(at)) at = at[String(step)];
    else return undefined;
  }
  return at;
}

function set(node: unknown, path: Path, value: unknown): void {
  const parent = get(node, path.slice(0, -1));
  const last = path.at(-1);
  if (last === undefined) return;
  if (Array.isArray(parent)) parent[Number(last)] = value;
  else if (isObject(parent)) parent[String(last)] = value;
}

/** What a form shows: references as written, literal secrets as `{set, preview}`. */
export function masked(doc: ConfigDocument): ConfigDocument {
  const shown = structuredClone(doc);
  for (const { path } of secretsOf(shown)) {
    const value = get(shown, path);
    if (typeof value === "string" && !value.includes("${")) set(shown, path, { set: true, preview: preview(value) });
  }
  return shown;
}

export const preview = (value: string) => (value.length > 8 ? `${value.slice(0, 3)}•••${value.slice(-2)}` : "•••");

/** The document as it would be written (typed secrets as references) and the secrets to keep. */
export function prepared(edited: ConfigDocument, current: ConfigDocument) {
  const doc = structuredClone(edited);
  const kept = new Map(secretsOf(current).map((s) => [s.name, s.path]));
  const pending: Record<string, string> = {};
  for (const { path, name } of secretsOf(doc)) {
    const value = get(doc, path);
    if (isObject(value)) {
      const typed = typeof value.value === "string" ? value.value : "";
      if (typed) {
        pending[name] = typed;
        set(doc, path, `\${secret:${name}}`);
      } else {
        const was = kept.get(name);
        set(doc, path, was ? get(current, was) : null);
      }
    } else if (typeof value === "string" && !value.includes("${")) {
      pending[name] = value;
      set(doc, path, `\${secret:${name}}`);
    }
  }
  return { doc, pending };
}

// -- checking --------------------------------------------------------------------------------------

const ENVIRON = new Set(["TELEGRAM_TOKEN"]);

function references(node: unknown, path: Path = []): { path: Path; name: string; secret: boolean }[] {
  if (typeof node === "string") {
    return [...node.matchAll(/\$\{(secret:)?([^}]+)\}/g)].map((m) => ({
      path,
      name: m[2] ?? "",
      secret: Boolean(m[1]),
    }));
  }
  if (Array.isArray(node)) return node.flatMap((v, i) => references(v, [...path, i]));
  if (isObject(node)) return Object.entries(node).flatMap(([k, v]) => references(v, [...path, k]));
  return [];
}

/** Where secrets are referred to: name → dotted paths. */
export function usedSecrets(doc: ConfigDocument): Record<string, string[]> {
  const used: Record<string, string[]> = {};
  for (const r of references(doc)) {
    if (r.secret) used[r.name] = [...(used[r.name] ?? []), r.path.join(".")];
  }
  return used;
}

function typeOk(node: JsonSchema, value: unknown): boolean {
  const types = Array.isArray(node.type) ? node.type : node.type ? [node.type] : [];
  if (!types.length) return true;
  return types.some((t) =>
    t === "string"
      ? typeof value === "string"
      : t === "integer"
        ? Number.isInteger(value)
        : t === "number"
          ? typeof value === "number"
          : t === "boolean"
            ? typeof value === "boolean"
            : t === "array"
              ? Array.isArray(value)
              : t === "object"
                ? isObject(value)
                : t === "null"
                  ? value === null
                  : true,
  );
}

type Found = { path: Path; code: string; detail: string };

function check(node: JsonSchema, root: JsonSchema, value: unknown, path: Path, out: Found[], lang: Lang): void {
  const schema = resolve(node, root);
  if (schema.anyOf) {
    const options = schema.anyOf.map((o) => resolve(o, root));
    const fits = options.find((o) => typeOk(o, value) && (o.type !== "null" || value === null));
    if (!fits) out.push({ path, code: "invalid", detail: lang === "fr" ? "valeur inattendue" : "unexpected value" });
    else if (fits.type !== "null") check(fits, root, value, path, out, lang);
    return;
  }
  if (schema.const !== undefined && value !== schema.const) {
    out.push({ path, code: "invalid", detail: `${lang === "fr" ? "attendu" : "expected"} ${String(schema.const)}` });
    return;
  }
  if (!typeOk(schema, value)) {
    const expected = Array.isArray(schema.type) ? schema.type.join("|") : schema.type;
    out.push({
      path,
      code: "invalid",
      detail: lang === "fr" ? `doit être de type ${expected}` : `Input should be a valid ${expected}`,
    });
    return;
  }
  if (schema.enum && !schema.enum.includes(value as string)) {
    out.push({ path, code: "invalid", detail: schema.enum.join(", ") });
  }
  if (typeof value === "string" && schema.minLength && value.length < schema.minLength) {
    out.push({
      path,
      code: "invalid",
      detail: lang === "fr" ? "ne peut pas être vide" : "String should have at least 1 character",
    });
  }
  if (typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum)
      out.push({ path, code: "invalid", detail: `≥ ${schema.minimum}` });
    if (schema.maximum !== undefined && value > schema.maximum)
      out.push({ path, code: "invalid", detail: `≤ ${schema.maximum}` });
    if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum)
      out.push({ path, code: "invalid", detail: `> ${schema.exclusiveMinimum}` });
  }
  if (isObject(value) && (schema.properties || schema.additionalProperties !== undefined)) {
    for (const name of schema.required ?? []) {
      if (value[name] === undefined) out.push({ path: [...path, name], code: "missing", detail: "" });
    }
    for (const [name, child] of Object.entries(value)) {
      const prop = schema.properties?.[name];
      if (prop) {
        if (child !== undefined) check(prop, root, child, [...path, name], out, lang);
      } else if (isObject(schema.additionalProperties)) {
        check(schema.additionalProperties, root, child, [...path, name], out, lang);
      } else if (schema.additionalProperties === false) {
        out.push({ path: [...path, name], code: "extra", detail: "" });
      }
    }
  }
  if (Array.isArray(value) && schema.items) {
    value.forEach((child, i) => {
      check(schema.items as JsonSchema, root, child, [...path, i], out, lang);
    });
  }
}

/** Nestor's checks: references resolve, sections and each component's settings validate. */
export function problems(
  db: ConfigDb,
  doc: ConfigDocument,
  pending: Record<string, string>,
  lang: Lang,
): ConfigProblem[] {
  const found: Found[] = [];
  for (const r of references(doc)) {
    if (r.secret ? !(r.name in pending || r.name in db.vault) : !ENVIRON.has(r.name))
      found.push({ path: r.path, code: r.secret ? "secret" : "reference", detail: r.name });
  }
  if (!found.length) {
    const schema = SCHEMAS[lang];
    for (const [key, section] of Object.entries(schema.sections) as [string, JsonSchema][]) {
      const value = doc[key];
      if (value === undefined) {
        if (key === "persona") found.push({ path: [key], code: "missing", detail: "" });
        continue;
      }
      if (key === "household") {
        if (!Array.isArray(value)) found.push({ path: [key], code: "invalid", detail: "list" });
        else for (const [i, person] of value.entries()) check(section, section, person, [key, i], found, lang);
      } else if (key === "data_dir") {
        if (typeof value !== "string") found.push({ path: [key], code: "invalid", detail: "string" });
      } else {
        check(section, section, value, [key], found, lang);
      }
    }
    for (const key of SLOTS) {
      const slot = schema.slots[key];
      const value = doc[key];
      if (!slot) continue;
      const empty = value === undefined || value === null || (Array.isArray(value) && !value.length);
      if (empty) {
        if (slot.required) found.push({ path: [key], code: "missing", detail: "" });
        continue;
      }
      const entries = slot.many ? (Array.isArray(value) ? value : [value]) : [value];
      entries.forEach((entry, i) => {
        const where: Path = slot.many ? [key, i] : [key];
        const kind = isObject(entry) ? (slot.kinds[String(entry.kind)] as JsonSchema | undefined) : undefined;
        if (!kind) {
          found.push({ path: [...where, "kind"], code: "unknown_kind", detail: String(isObject(entry) && entry.kind) });
          return;
        }
        check(kind, kind, entry, where, found, lang);
      });
    }
    const known = new Set([...Object.keys(schema.sections), ...SLOTS]);
    for (const key of Object.keys(doc)) {
      if (!known.has(key)) found.push({ path: [key], code: "extra", detail: "" });
    }
  }
  return found.map(({ path, code, detail }) => {
    const id = `config-error-${code.replace(/_/g, "-")}`;
    const args = { path: path.join("."), detail };
    return { path, code, message_id: id, args, message: render(lang, { id, args }) };
  });
}

// -- the changes ---------------------------------------------------------------------------------

function flat(node: unknown, path = ""): Record<string, unknown> {
  if (isObject(node))
    return Object.assign({}, ...Object.entries(node).map(([k, v]) => flat(v, path ? `${path}.${k}` : k)));
  if (Array.isArray(node)) return Object.assign({}, ...node.map((v, i) => flat(v, path ? `${path}.${i}` : String(i))));
  return { [path]: node };
}

export function diff(before: ConfigDocument, after: ConfigDocument, pending: Record<string, string>): S["DiffOut"] {
  const a = flat(before);
  const b = flat(after);
  const secret = new Set([...secretsOf(after), ...secretsOf(before)].map((s) => s.path.join(".")));
  const typed = new Set(
    secretsOf(after)
      .filter((s) => s.name in pending)
      .map((s) => s.path.join(".")),
  );
  const out: S["DiffOut"] = { added: [], removed: [], changed: [] };
  const change = (path: string, was: unknown, is: unknown): Change => {
    const hidden = secret.has(path);
    return { path, before: hidden ? null : was, after: hidden ? null : is, secret: hidden };
  };
  for (const path of Object.keys(b)
    .filter((p) => !(p in a))
    .sort())
    out.added.push(change(path, null, b[path]));
  for (const path of Object.keys(a)
    .filter((p) => !(p in b))
    .sort())
    out.removed.push(change(path, a[path], null));
  for (const path of Object.keys(a)
    .filter((p) => p in b)
    .sort()) {
    if (a[path] !== b[path] || typed.has(path)) out.changed.push(change(path, a[path], b[path]));
  }
  return out;
}

export const changedPaths = (d: S["DiffOut"]) => [...d.added, ...d.removed, ...d.changed].map((c) => c.path);
