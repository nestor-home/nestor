import { describe, expect, it } from "vitest";
import type { JsonSchema } from "@/api";
import schemaFr from "@/mocks/config/schema.fr.json";
import { controlOf, fieldsOf, getAt, problemsUnder, resolve, setAt, typedSecret } from "./schema";

const SCHEMA = schemaFr as unknown as {
  sections: Record<string, JsonSchema>;
  slots: Record<string, { kinds: Record<string, JsonSchema> }>;
};
const mcp = SCHEMA.slots.tools?.kinds.mcp as JsonSchema;
const voice = SCHEMA.slots.channels?.kinds.voice as JsonSchema;
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
    expect(controlOf(prop(voice, "speech"), voice, "speech")).toBe("object");
    expect(controlOf(prop(voice, "allow_unpaired_browser"), voice, "allow_unpaired_browser")).toBe("boolean");
    expect(controlOf(prop(voice, "fallback_clips"), voice, "fallback_clips")).toBe("path");
    expect(controlOf(prop(voice, "style"), voice, "style")).toBe("long-text");
  });

  it("unwraps a nullable value and keeps the property's own bounds and default", () => {
    const port = resolve(prop(voice, "port"), voice);
    expect(port.nullable).toBe(true);
    expect(port.schema).toMatchObject({ type: "integer", minimum: 0, maximum: 65535, default: 7860 });
  });

  it("folds the advanced settings apart, and never shows the kind", () => {
    const initiative = SCHEMA.sections.initiative as JsonSchema;
    const { plain, advanced } = fieldsOf(initiative);
    expect(plain.map(([n]) => n)).toEqual(["quiet_hours", "main_room"]);
    expect(advanced.map(([n]) => n)).toEqual(["follow_up_after_s"]);
    expect(fieldsOf(mcp).plain.map(([n]) => n)).not.toContain("kind");
  });
});

describe("editing a document", () => {
  const doc = { persona: { name: "Richie" }, channels: [{ kind: "voice" }, { kind: "telegram" }] };

  it("writes at a path without touching the original, and removes a key set to undefined", () => {
    const next = setAt(doc, ["persona", "name"], "Alfred");
    expect(getAt(next, ["persona", "name"])).toBe("Alfred");
    expect(doc.persona.name).toBe("Richie");
    expect(setAt(doc, ["persona", "name"], undefined)).toEqual({ ...doc, persona: {} });
    expect(setAt(doc, ["channels", 0, "room"], "salon").channels[0]).toEqual({ kind: "voice", room: "salon" });
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
