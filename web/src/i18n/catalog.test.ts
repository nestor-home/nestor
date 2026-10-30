/**
 * The catalogues are complete and the components hold no text of their own:
 * - every locale has the same messages, file by file, and parses without errors;
 * - every id the code asks for (`t("…")`, `tr("…")`, `<Localized id="…">`) exists;
 * - no JSX text or user-facing attribute in features, components and routes is a literal.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { parse } from "@fluent/syntax";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { LOCALES, sourcesOf } from "./catalog";

const ROOT = join(__dirname, "..");
const SCANNED = ["features", "components", "routes"];
const ATTRIBUTES = new Set([
  "aria-label",
  "title",
  "placeholder",
  "alt",
  "label",
  "description",
  "hint",
  "empty",
  "confirm",
  "action",
]);
/** Text that is not language: punctuation, symbols, keyboard keys, the wordmark. */
const ALLOWED = (text: string) => !/\p{L}{2,}/u.test(text) || ["nestor", "⌘K"].includes(text.trim());

function ids(locale: (typeof LOCALES)[number]): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>();
  for (const [file, text] of Object.entries(sourcesOf(locale))) {
    const resource = parse(text, {});
    const junk = resource.body.filter((e) => e.type === "Junk");
    expect(junk, `${locale}/${file} has syntax errors`).toEqual([]);
    out.set(
      file,
      new Set(resource.body.flatMap((e) => (e.type === "Message" || e.type === "Term" ? [e.id.name] : []))),
    );
  }
  return out;
}

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.tsx?$/.test(name) && !name.includes(".test.") && !name.endsWith(".gen.ts") ? [path] : [];
  });
}

const SOURCES = SCANNED.flatMap((d) => files(join(ROOT, d)));

describe("the catalogues", () => {
  it("hold the same messages in every locale", () => {
    const en = ids("en");
    for (const locale of LOCALES) {
      const other = ids(locale);
      expect([...other.keys()].sort(), `${locale} files`).toEqual([...en.keys()].sort());
      for (const [file, set] of en)
        expect([...(other.get(file) ?? [])].sort(), `${locale}/${file}`).toEqual([...set].sort());
    }
  });

  it("define every id the code asks for", () => {
    const known = new Set([...ids("en").values()].flatMap((s) => [...s]));
    const asked = new Set<string>();
    for (const path of [...SOURCES, ...files(join(ROOT, "lib"))]) {
      const text = readFileSync(path, "utf8");
      for (const m of text.matchAll(/\b(?:t|tr)\(\s*"([a-z0-9-]+)"/g)) asked.add(m[1] as string);
      for (const m of text.matchAll(/<Localized\s+id="([a-z0-9-]+)"/g)) asked.add(m[1] as string);
    }
    expect([...asked].filter((id) => !known.has(id)).sort()).toEqual([]);
  });
});

describe("components", () => {
  it("say nothing that is not in a catalogue", () => {
    const literals: string[] = [];
    for (const path of SOURCES) {
      const source = ts.createSourceFile(
        path,
        readFileSync(path, "utf8"),
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX,
      );
      const where = (node: ts.Node) =>
        `${relative(ROOT, path)}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1}`;
      const visit = (node: ts.Node) => {
        if (ts.isJsxText(node) && !ALLOWED(node.text)) literals.push(`${where(node)} ${node.text.trim()}`);
        if (ts.isJsxAttribute(node) && ATTRIBUTES.has(node.name.getText()) && node.initializer) {
          const init = node.initializer;
          const value = ts.isStringLiteral(init)
            ? init.text
            : ts.isJsxExpression(init) && init.expression && ts.isStringLiteralLike(init.expression)
              ? init.expression.text
              : null;
          if (value !== null && !ALLOWED(value)) literals.push(`${where(node)} ${node.name.getText()}="${value}"`);
        }
        if (
          ts.isJsxExpression(node) &&
          node.expression &&
          ts.isStringLiteralLike(node.expression) &&
          ts.isJsxElement(node.parent) &&
          !ALLOWED(node.expression.text)
        ) {
          literals.push(`${where(node)} {"${node.expression.text}"}`);
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }
    expect(literals).toEqual([]);
  });

  it("carry no French left in code strings (the catalogue holds it)", () => {
    const french: string[] = [];
    for (const path of [...SOURCES, ...files(join(ROOT, "lib"))]) {
      const source = ts.createSourceFile(
        path,
        readFileSync(path, "utf8"),
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX,
      );
      const visit = (node: ts.Node) => {
        const text =
          ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)
            ? node.text
            : ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)
              ? node.text
              : null;
        // language names are written in their own language (the language switcher)
        if (text && /[àâçéèêëîïôûùüœ]/i.test(text) && text !== "Français" && !ts.isImportDeclaration(node.parent)) {
          french.push(
            `${relative(ROOT, path)}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1} ${text}`,
          );
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }
    expect(french).toEqual([]);
  });
});

/** The plain text of each message of a locale (placeables kept as written). */
function texts(locale: (typeof LOCALES)[number]): Map<string, string> {
  const out = new Map<string, string>();
  for (const text of Object.values(sourcesOf(locale))) {
    for (const line of text.split("\n")) {
      const m = line.match(/^([a-z][\w-]*) = (.*)$/);
      if (m?.[1] && m[2] !== undefined) out.set(m[1], m[2]);
    }
  }
  return out;
}

const OPENERS =
  /^(ici,? vous pouvez|gérez|cette page|sur cette page|here you can|manage|this page|on this page|welcome)/i;
const normal = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/[^\p{L}\p{N} ]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();

describe("the copy says something", () => {
  it("never restates a title in its description, nor opens on filler", () => {
    const found: string[] = [];
    for (const locale of LOCALES) {
      const all = texts(locale);
      for (const [id, text] of all) {
        const m = id.match(/^(.*)-(intro|description|hint|text|subtitle)$/);
        if (!m) continue;
        if (OPENERS.test(text.trim())) found.push(`${locale}: ${id} opens on filler`);
        const title = all.get(`${m[1]}-title`);
        if (!title || title.includes("{")) continue;
        const t = normal(title);
        const d = normal(text);
        if (t.length >= 4 && (d === t || d.startsWith(`${t} `) || d.startsWith(`${t}.`)))
          found.push(`${locale}: ${id} restates ${m[1]}-title`);
      }
    }
    expect(found).toEqual([]);
  });
});
