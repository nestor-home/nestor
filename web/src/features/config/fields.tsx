/**
 * The schema-driven form: one control per property of a JSON Schema, on the shadcn components.
 * Every control reads and writes the editor's draft at its path and shows the problems the
 * preview located there.
 */
import { ArrowDown, ArrowUp, ChevronRight, KeyRound, Plus, X } from "lucide-react";
import { type ReactNode, useId, useState } from "react";
import type { ConfigProblem, JsonSchema } from "@/api";
import { Choice } from "@/components/choice";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import { hasMessage, tr } from "@/i18n/runtime";
import { cn } from "@/lib/utils";
import { useConfigEditor } from "./editor";
import {
  type Control,
  controlOf,
  defaultText,
  fieldsOf,
  getAt,
  helpOf,
  isRecord,
  isReference,
  isShown,
  isTyped,
  keyOf,
  move,
  type Path,
  problemsByPath,
  problemsUnder,
  resolve,
  titleOf,
  typedSecret,
} from "./schema";

const idOf = (path: Path) => `cfg-${path.join("-").replace(/[^\w-]/g, "_")}`;

/** A located problem said at its field: the field's own label instead of the dotted path. */
export function problemText(problem: ConfigProblem, label?: string): string {
  if (hasMessage(problem.message_id))
    return tr(problem.message_id, { ...problem.args, path: label ?? keyOf(problem.path) });
  const path = String(problem.args.path ?? "");
  if (label && path && problem.message.startsWith(path)) return `${label}${problem.message.slice(path.length)}`;
  return problem.message;
}

/** The properties of an object schema at `path`: the plain ones, then the advanced ones folded. */
export function ObjectFields({
  schema,
  root,
  path,
  className,
}: {
  schema: JsonSchema;
  root: JsonSchema;
  path: Path;
  className?: string;
}) {
  const t = useT();
  const { problems } = useConfigEditor();
  const object = resolve(schema, root).schema;
  const { plain, advanced } = fieldsOf(object);
  const required = new Set(object.required ?? []);
  const advancedTrouble = advanced.some(([name]) => problemsUnder(problems, [...path, name]).length > 0);
  return (
    <div className={cn("@container", className)}>
      <div className="grid gap-x-6 gap-y-5 @xl:grid-cols-2">
        {plain.map(([name, node]) => (
          <Property
            key={name}
            name={name}
            node={node}
            root={root}
            path={[...path, name]}
            required={required.has(name)}
          />
        ))}
        {advanced.length ? (
          <Collapsible
            key={advancedTrouble ? "open" : "closed"}
            defaultOpen={advancedTrouble}
            className="@xl:col-span-2"
          >
            <CollapsibleTrigger className="group/adv inline-flex items-center gap-1.5 rounded-sm font-mono text-[0.72rem] tracking-wide text-ink-muted uppercase hover:text-ink">
              <ChevronRight
                className="size-3.5 transition-transform group-data-panel-open/adv:rotate-90"
                aria-hidden="true"
              />
              {t("cfg-advanced", { count: advanced.length })}
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="mt-4 grid gap-x-6 gap-y-5 border-t border-dashed border-rule pt-5 @xl:grid-cols-2">
                {advanced.map(([name, node]) => (
                  <Property
                    key={name}
                    name={name}
                    node={node}
                    root={root}
                    path={[...path, name]}
                    required={required.has(name)}
                  />
                ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        ) : null}
      </div>
    </div>
  );
}

const WIDE: Control[] = ["long-text", "object", "list", "map", "json"];

/** One property: its label, control, help and problems. */
export function Property({
  name,
  node,
  root,
  path,
  required,
}: {
  name: string;
  node: JsonSchema;
  root: JsonSchema;
  path: Path;
  required: boolean;
}) {
  const { draft, problems } = useConfigEditor();
  const value = getAt(draft, path);
  const control = controlOf(node, root, name, value);
  if (control === "const") return null;
  const label = titleOf(node, name);
  const here = problemsByPath(problems).get(keyOf(path)) ?? [];
  const id = idOf(path);
  if (control === "object") {
    const nested = problemsUnder(problems, path).filter((p) => keyOf(p.path) !== keyOf(path));
    return (
      <fieldset className="grid min-w-0 gap-4 rounded-md border border-rule px-4 pt-2 pb-4 @xl:col-span-2">
        <legend className="px-1.5 font-serif text-[1.05rem] text-ink">{label}</legend>
        {helpOf(node) ? <p className="-mt-1 text-xs text-ink-muted">{helpOf(node)}</p> : null}
        <ObjectFields schema={node} root={root} path={path} />
        <Problems problems={here} label={label} />
        {nested.length && !isRecord(value) ? <Problems problems={nested} /> : null}
      </fieldset>
    );
  }
  return (
    <FieldFrame
      id={id}
      label={label}
      help={helpOf(node)}
      problems={here}
      wide={WIDE.includes(control)}
      required={required}
      control={control}
    >
      <ControlFor control={control} id={id} node={node} root={root} path={path} required={required} label={label} />
    </FieldFrame>
  );
}

function FieldFrame({
  id,
  label,
  help,
  problems,
  wide,
  control,
  children,
}: {
  id: string;
  label: string;
  help: string | null;
  problems: ConfigProblem[];
  wide: boolean;
  required: boolean;
  control: Control;
  children: ReactNode;
}) {
  const inline = control === "boolean";
  return (
    <div
      className={cn("grid min-w-0 content-start gap-1.5", wide && "@xl:col-span-2")}
      data-invalid={problems.length ? "" : undefined}
    >
      {inline ? null : (
        <Label htmlFor={id} className="text-[0.8rem] font-medium text-ink">
          {label}
        </Label>
      )}
      {children}
      {help ? (
        <p id={`${id}-help`} className="text-xs text-pretty text-ink-muted">
          {help}
        </p>
      ) : null}
      <Problems problems={problems} label={label} id={`${id}-problem`} />
    </div>
  );
}

export function Problems({ problems, label, id }: { problems: ConfigProblem[]; label?: string; id?: string }) {
  if (!problems.length) return null;
  return (
    <ul id={id} className="grid gap-0.5">
      {problems.map((p) => (
        <li key={`${keyOf(p.path)}:${p.code}:${p.message}`} className="text-xs text-brick">
          {problemText(p, label)}
        </li>
      ))}
    </ul>
  );
}

interface ControlProps {
  id: string;
  node: JsonSchema;
  root: JsonSchema;
  path: Path;
  required: boolean;
  label: string;
}

function described(id: string, node: JsonSchema, invalid: boolean) {
  const ids = [helpOf(node) ? `${id}-help` : null, invalid ? `${id}-problem` : null].filter(Boolean);
  return {
    "aria-describedby": ids.length ? ids.join(" ") : undefined,
    "aria-invalid": invalid || undefined,
  };
}

function ControlFor({ control, ...props }: ControlProps & { control: Control }) {
  switch (control) {
    case "secret":
      return <SecretControl {...props} />;
    case "enum":
      return <EnumControl {...props} />;
    case "boolean":
      return <BooleanControl {...props} />;
    case "integer":
    case "number":
      return <NumberControl {...props} integer={control === "integer"} />;
    case "list":
      return <ListControl {...props} />;
    case "map":
      return <MapControl {...props} />;
    case "json":
      return <JsonControl {...props} />;
    default:
      return <TextControl {...props} long={control === "long-text"} mono={control === "path"} />;
  }
}

function useField(path: Path, required: boolean, nullable: boolean) {
  const { draft, set, problems } = useConfigEditor();
  const value = getAt(draft, path);
  const invalid = (problemsByPath(problems).get(keyOf(path)) ?? []).length > 0;
  /** An emptied field: the default applies, or `null` when the setting takes it, or empty text. */
  const clear = () => set(path, required ? (nullable ? null : "") : undefined);
  return { value, invalid, set: (next: unknown) => set(path, next), clear };
}

function TextControl({ id, node, root, path, required, long, mono }: ControlProps & { long: boolean; mono: boolean }) {
  const { nullable } = resolve(node, root);
  const field = useField(path, required, nullable);
  const text = typeof field.value === "string" ? field.value : "";
  const placeholder = defaultText(node, root) ?? undefined;
  const common = {
    id,
    value: text,
    placeholder,
    ...described(id, node, field.invalid),
    onChange: (e: { target: { value: string } }) => (e.target.value === "" ? field.clear() : field.set(e.target.value)),
  };
  if (long) return <Textarea {...common} rows={3} className="min-h-20" />;
  return <Input {...common} className={cn(mono && "font-mono text-[0.82rem]")} spellCheck={!mono} />;
}

function NumberControl({ id, node, root, path, required, integer }: ControlProps & { integer: boolean }) {
  const { schema, nullable } = resolve(node, root);
  const field = useField(path, required, nullable);
  const text = typeof field.value === "number" ? String(field.value) : "";
  const minimum = schema.minimum ?? schema.exclusiveMinimum;
  return (
    <Input
      id={id}
      type="number"
      inputMode={integer ? "numeric" : "decimal"}
      step={integer ? 1 : "any"}
      min={minimum}
      max={schema.maximum}
      value={text}
      placeholder={defaultText(node, root) ?? undefined}
      className="font-mono text-[0.82rem] tabular sm:max-w-48"
      {...described(id, node, field.invalid)}
      onChange={(e) => {
        const raw = e.target.value;
        if (raw === "") return field.clear();
        const parsed = Number(raw);
        if (!Number.isNaN(parsed)) field.set(integer ? Math.trunc(parsed) : parsed);
      }}
    />
  );
}

function EnumControl({ id, node, root, path, required }: ControlProps) {
  const t = useT();
  const { schema, nullable } = resolve(node, root);
  const field = useField(path, required, nullable);
  const fallback = defaultText(node, root);
  const options = (schema.enum ?? []).map((v) => ({ value: String(v), label: String(v) }));
  const all = required ? options : [{ value: "", label: t("cfg-default", { value: fallback ?? "∅" }) }, ...options];
  const value = field.value === undefined || field.value === null ? "" : String(field.value);
  return (
    <Choice
      id={id}
      value={value}
      options={all}
      className="sm:max-w-72"
      describedBy={described(id, node, field.invalid)["aria-describedby"]}
      onChange={(next) => (next === "" ? field.clear() : field.set(next))}
    />
  );
}

function BooleanControl({ id, node, root, path, required, label }: ControlProps) {
  const field = useField(path, required, false);
  const fallback = resolve(node, root).schema.default ?? node.default;
  const checked = typeof field.value === "boolean" ? field.value : fallback === true;
  return (
    <div className="flex items-center gap-3 pt-1">
      <Switch id={id} checked={checked} onCheckedChange={(on) => field.set(on)} {...described(id, node, false)} />
      <Label htmlFor={id} className="text-[0.85rem] text-ink">
        {label}
      </Label>
    </div>
  );
}

/** A secret never comes back: "set · preview", replaced by typing, kept by leaving it. */
function SecretControl({ id, node, root, path, required, label }: ControlProps) {
  const t = useT();
  const { base } = useConfigEditor();
  const { nullable } = resolve(node, root);
  const field = useField(path, required, nullable);
  const before = getAt(base, path);
  const [replacing, setReplacing] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const value = field.value;
  const keep = () => {
    setReplacing(false);
    setText(null);
    field.set(before);
  };
  const editable =
    replacing || text !== null || isTyped(value) || value === undefined || value === null || value === "";
  if (!editable && (isShown(value) || isReference(value))) {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-rule bg-paper-sunken/60 px-3 py-1.5">
        <KeyRound className="size-3.5 text-ink-faint" aria-hidden="true" />
        <span id={id} className="min-w-0 flex-1 font-mono text-[0.78rem] [overflow-wrap:anywhere] text-ink">
          {isShown(value)
            ? value.set
              ? t("cfg-secret-set", { preview: value.preview ?? "•••" })
              : t("cfg-secret-unset")
            : t("cfg-secret-reference", { reference: value })}
        </span>
        <Button
          variant="ghost"
          size="xs"
          onClick={() => setReplacing(true)}
          aria-label={t("cfg-secret-replace-label", { field: label })}
        >
          {t("cfg-secret-replace")}
        </Button>
      </div>
    );
  }
  // what this field shows while typed: never the reference or preview it replaces
  const typed = text ?? (isTyped(value) ? value.value : "");
  const canKeep = before !== undefined && before !== null && (isShown(before) || isReference(before));
  return (
    <div className="flex items-center gap-2">
      <Input
        id={id}
        type="password"
        autoComplete="new-password"
        spellCheck={false}
        autoFocus={replacing}
        value={typed}
        placeholder={t("cfg-secret-placeholder")}
        className="font-mono text-[0.82rem]"
        {...described(id, node, field.invalid)}
        onChange={(e) => {
          setText(e.target.value);
          field.set(e.target.value === "" ? (canKeep ? before : undefined) : typedSecret(e.target.value));
        }}
      />
      {canKeep ? (
        <Button variant="ghost" size="sm" onClick={keep}>
          {t("cfg-secret-keep")}
        </Button>
      ) : null}
    </div>
  );
}

function ItemButtons({
  index,
  count,
  label,
  onMove,
  onRemove,
}: {
  index: number;
  count: number;
  label: string;
  onMove: (by: -1 | 1) => void;
  onRemove: () => void;
}) {
  const t = useT();
  return (
    <span className="flex shrink-0 items-center">
      <Button
        variant="ghost"
        size="icon-sm"
        disabled={index === 0}
        onClick={() => onMove(-1)}
        aria-label={t("cfg-move-up", { item: label })}
      >
        <ArrowUp />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        disabled={index === count - 1}
        onClick={() => onMove(1)}
        aria-label={t("cfg-move-down", { item: label })}
      >
        <ArrowDown />
      </Button>
      <Button variant="ghost" size="icon-sm" onClick={onRemove} aria-label={t("cfg-remove-item", { item: label })}>
        <X />
      </Button>
    </span>
  );
}

/** A list of short texts: add, remove, reorder. */
function ListControl({ id, node, root, path, required, label }: ControlProps) {
  const t = useT();
  const { nullable } = resolve(node, root);
  const field = useField(path, required, nullable);
  const { problems } = useConfigEditor();
  const items = Array.isArray(field.value) ? (field.value as unknown[]).map((v) => String(v ?? "")) : [];
  const fallback = defaultText(node, root);
  const write = (next: string[]) => (next.length || required ? field.set(next) : field.clear());
  return (
    <div className="grid gap-1.5">
      {items.length ? (
        <ol className="grid gap-1.5">
          {items.map((item, index) => {
            const itemLabel = item || t("cfg-item-n", { n: index + 1 });
            const itemProblems = problemsByPath(problems).get(keyOf([...path, index])) ?? [];
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: the position is the item's identity while it is edited
              <li key={index} className="grid gap-0.5">
                <div className="flex items-center gap-1">
                  <Input
                    id={index === 0 ? id : `${id}-${index}`}
                    value={item}
                    aria-label={t("cfg-item-of", { field: label, n: index + 1 })}
                    aria-invalid={itemProblems.length ? true : undefined}
                    className="font-mono text-[0.82rem]"
                    onChange={(e) => write(items.map((v, i) => (i === index ? e.target.value : v)))}
                  />
                  <ItemButtons
                    index={index}
                    count={items.length}
                    label={itemLabel}
                    onMove={(by) => write(move(items, index, by))}
                    onRemove={() => write(items.filter((_, i) => i !== index))}
                  />
                </div>
                <Problems problems={itemProblems} label={itemLabel} />
              </li>
            );
          })}
        </ol>
      ) : (
        <p id={id} className="text-xs text-ink-faint">
          {fallback ? t("cfg-list-default", { value: fallback }) : t("cfg-list-empty")}
        </p>
      )}
      <Button variant="outline" size="sm" className="justify-self-start" onClick={() => write([...items, ""])}>
        <Plus /> {t("cfg-add-item")}
      </Button>
    </div>
  );
}

/** A map of names to values (headers, risks, people to entities). */
function MapControl({ id, node, root, path, required, label }: ControlProps) {
  const t = useT();
  const { schema, nullable } = resolve(node, root);
  const field = useField(path, required, nullable);
  const valueSchema = isRecord(schema.additionalProperties) ? (schema.additionalProperties as JsonSchema) : {};
  const entries = isRecord(field.value) ? Object.entries(field.value) : [];
  const write = (next: [string, unknown][]) =>
    next.length || required ? field.set(Object.fromEntries(next)) : field.clear();
  const valueControl = controlOf(valueSchema, root);
  const options = (resolve(valueSchema, root).schema.enum ?? []).map((v) => ({ value: String(v), label: String(v) }));
  return (
    <div className="grid gap-1.5">
      {entries.length ? (
        <ul className="grid gap-1.5">
          {entries.map(([key, value], index) => {
            const rowId = index === 0 ? id : `${id}-${index}`;
            const setValue = (v: unknown) => write(entries.map(([k, old], i) => [k, i === index ? v : old]));
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: the key itself is being edited
              <li key={index} className="flex flex-wrap items-center gap-1.5 sm:flex-nowrap">
                <Input
                  id={rowId}
                  value={key}
                  aria-label={t("cfg-map-key", { field: label, n: index + 1 })}
                  className="font-mono text-[0.82rem] sm:max-w-56"
                  onChange={(e) => write(entries.map(([k, v], i) => [i === index ? e.target.value : k, v]))}
                />
                <span aria-hidden="true" className="font-mono text-xs text-ink-faint">
                  →
                </span>
                {valueControl === "enum" ? (
                  <Choice
                    id={`${rowId}-value`}
                    value={String(value ?? "")}
                    options={options}
                    className="sm:max-w-44"
                    onChange={setValue}
                  />
                ) : valueControl === "secret" ? (
                  <Input
                    id={`${rowId}-value`}
                    type="password"
                    autoComplete="new-password"
                    value={isTyped(value) ? value.value : typeof value === "string" ? value : ""}
                    placeholder={isShown(value) ? t("cfg-secret-set", { preview: value.preview ?? "•••" }) : undefined}
                    aria-label={t("cfg-map-value", { field: label, key: key || index + 1 })}
                    className="font-mono text-[0.82rem]"
                    onChange={(e) => setValue(e.target.value)}
                  />
                ) : (
                  <Input
                    id={`${rowId}-value`}
                    value={typeof value === "string" ? value : JSON.stringify(value ?? "")}
                    aria-label={t("cfg-map-value", { field: label, key: key || index + 1 })}
                    className="font-mono text-[0.82rem]"
                    onChange={(e) => setValue(e.target.value)}
                  />
                )}
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => write(entries.filter((_, i) => i !== index))}
                  aria-label={t("cfg-remove-item", { item: key || t("cfg-item-n", { n: index + 1 }) })}
                >
                  <X />
                </Button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p id={id} className="text-xs text-ink-faint">
          {t("cfg-list-empty")}
        </p>
      )}
      <Button
        variant="outline"
        size="sm"
        className="justify-self-start"
        disabled={entries.some(([k]) => k === "")}
        onClick={() => write([...entries, ["", valueControl === "enum" ? (options[0]?.value ?? "") : ""]])}
      >
        <Plus /> {t("cfg-add-entry")}
      </Button>
    </div>
  );
}

/** Free-form settings (passed through to a provider as they are): JSON, checked when leaving it. */
function JsonControl({ id, node, root, path, required }: ControlProps) {
  const t = useT();
  const { nullable } = resolve(node, root);
  const field = useField(path, required, nullable);
  const written = field.value === undefined ? "" : JSON.stringify(field.value, null, 2);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const errorId = useId();
  return (
    <div className="grid gap-1">
      <Textarea
        id={id}
        value={text ?? written}
        rows={3}
        spellCheck={false}
        placeholder={defaultText(node, root) ?? "{}"}
        className="min-h-20 font-mono text-[0.78rem]"
        aria-invalid={error || field.invalid || undefined}
        aria-describedby={error ? errorId : described(id, node, field.invalid)["aria-describedby"]}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          if (text === null) return;
          if (text.trim() === "") {
            field.clear();
            setText(null);
            setError(false);
            return;
          }
          try {
            field.set(JSON.parse(text));
            setText(null);
            setError(false);
          } catch {
            setError(true);
          }
        }}
      />
      {error ? (
        <p id={errorId} className="text-xs text-brick">
          {t("cfg-json-invalid")}
        </p>
      ) : null}
    </div>
  );
}
