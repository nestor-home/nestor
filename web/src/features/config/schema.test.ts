import { describe, expect, it } from "vitest";
import type { JsonSchema } from "@/api";
import schemaFr from "@/mocks/config/schema.fr.json";
import { controlOf, getAt, problemsUnder, resolve, setAt, typedSecret } from "./schema";

const SCHEMA = schemaFr as unknown as {
  sections: Record<string, JsonSchema>;
  slots: Record<string, { kinds: Record<string, JsonSchema> }>;
};
const mcp = SCHEMA.slots.tools?.kinds.mcp as JsonSchema;
const satellites = SCHEMA.slots.channels?.kinds.satellites as JsonSchema;
const prop = (root: JsonSchema, name: string) => root.properties?.[name] as JsonSchema;

describe("reading a plugin's schema (as a real instance sends it)", () => {
  it("picks a control for every kind of setting", () => {
    expect(controlOf(prop(mcp, "url"), mcp, "url")).toBe("text");
    expect(controlOf(prop(mcp, "transport"), mcp, "transport")).toBe("enum"); // through $ref
    expect(controlOf(prop(mcp, "token"), mcp, "token")).toBe("secret"); // password inside anyOf
    expect(controlOf(prop(mcp, "headers"), mcp, "headers")).toBe("map");
    expect(controlOf(prop(mcp, "risks"), mcp, "risks")).toBe("map");
    expect(controlOf(prop(mcp, "include"), mcp, "include")).toBe("list"); // a list, or null
    expect(controlOf(prop(mcp, "max_result_chars"), mcp, "max_result_chars")).toBe("integer");
    expect(controlOf(prop(mcp, "timeout_s"), mcp, "timeout_s")).toBe("number");
    expect(controlOf(prop(mcp, "kind"), mcp, "kind")).toBe("const");
    expect(controlOf(prop(satellites, "voice"), satellites, "voice")).toBe("object"); // an object, or null
    const voice = resolve(prop(satellites, "voice"), satellites).schema;
    expect(controlOf(prop(voice, "speech"), satellites, "speech")).toBe("object");
    expect(controlOf(prop(voice, "fallback_clips"), satellites, "fallback_clips")).toBe("path");
    expect(controlOf(prop(voice, "style"), satellites, "style")).toBe("long-text");
    expect(controlOf({ type: "boolean" }, satellites, "enabled")).toBe("boolean");
  });

  it("unwraps a nullable value and keeps the property's own bounds and default", () => {
    const window = resolve(prop(satellites, "conversation_ends_after_s"), satellites);
    expect(window.nullable).toBe(true);
    expect(window.schema).toMatchObject({ type: "number", exclusiveMinimum: 0 });
    const port = resolve(prop(satellites, "port"), satellites);
    expect(port.nullable).toBe(false);
    expect(port.schema).toMatchObject({ type: "integer", minimum: 0, maximum: 65535, default: 8471 });
  });

  it("leaves a model's key optional, for a local server that needs none", () => {
    const model = SCHEMA.slots.models?.kinds["openai-compatible"] as JsonSchema;
    expect(controlOf(prop(model, "api_key"), model, "api_key")).toBe("secret");
    expect(resolve(prop(model, "api_key"), model).nullable).toBe(true);
  });
});

describe("editing a document", () => {
  const doc = { persona: { name: "Richie" }, channels: [{ kind: "satellites" }, { kind: "telegram" }] };

  it("writes at a path without touching the original, and removes a key set to undefined", () => {
    const next = setAt(doc, ["persona", "name"], "Alfred");
    expect(getAt(next, ["persona", "name"])).toBe("Alfred");
    expect(doc.persona.name).toBe("Richie");
    expect(setAt(doc, ["persona", "name"], undefined)).toEqual({ ...doc, persona: {} });
    expect(setAt(doc, ["channels", 0, "port"], 8472).channels[0]).toEqual({ kind: "satellites", port: 8472 });
  });

  it("sends a typed secret as a value, and a reference as written", () => {
    expect(typedSecret("sk-123")).toEqual({ value: "sk-123" });
    expect(typedSecret(`\${OPENAI_KEY}`)).toBe(`\${OPENAI_KEY}`);
  });

  it("finds the problems under a component, not its neighbours'", () => {
    const problems = [
      { path: ["channels", 0, "room"], code: "invalid", message_id: "x", args: {}, message: "" },
      { path: ["channels", 1, "token"], code: "missing", message_id: "x", args: {}, message: "" },
      { path: ["channels", 10], code: "invalid", message_id: "x", args: {}, message: "" },
    ];
    expect(problemsUnder(problems, ["channels", 1])).toHaveLength(1);
    expect(problemsUnder(problems, ["channels"])).toHaveLength(3);
  });
});
