import { ArrowDown, ArrowUp, CircleAlert, Pencil, Plus, Trash2 } from "lucide-react";
import { type ReactElement, type ReactNode, useId, useState } from "react";
import type { ConfigSlot, JsonSchema } from "@/api";
import { Confirm } from "@/components/confirm";
import { FormActions } from "@/components/form-actions";
import { FormDialog, FormSheet } from "@/components/overlay-form";
import { Panel, Section } from "@/components/page";
import { Empty } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useT } from "@/i18n";
import { brandName, brandOf, KindMark } from "@/lib/brands";
import { cn } from "@/lib/utils";
import { useConfigEditor } from "./editor";
import { ObjectFields, Problems } from "./fields";
import { freeName, getAt, isRecord, move, NAME, type Path, problemsUnder, renamed } from "./schema";
import { type ConfigPage, pageTitle } from "./sections";

/**
 * What a component's mark shows: the provider one of its fields names, by the hosts the runtime
 * recognises in it (`x-nestor.brands`, as the runtime itself brands a model), else its kind.
 */
export function markOf(kind: string, entry: Record<string, unknown>, schema: unknown): string {
  const fields = isRecord(schema) && isRecord(schema.properties) ? Object.entries(schema.properties) : [];
  for (const [name, field] of fields) {
    const brands = isRecord(field) && isRecord(field["x-nestor"]) ? field["x-nestor"].brands : undefined;
    const value = entry[name];
    if (!isRecord(brands) || typeof value !== "string" || !URL.canParse(value)) continue;
    const host = new URL(value).hostname;
    const found = Object.entries(brands).find(([suffix]) => host === suffix || host.endsWith(`.${suffix}`));
    if (typeof found?.[1] === "string") return found[1];
  }
  return kind;
}

/** The title of a plugin kind: its brand's name when it has one. */
export function kindTitle(kind: string): string {
  const slug = brandOf(kind);
  return slug ? brandName(slug) : kind;
}

export function ConfigPageView({ page }: { page: ConfigPage }) {
  if (page.kind === "household") return <HouseholdPage page={page} />;
  if (page.kind === "slots") return <SlotsPage page={page} />;
  return <SectionPage page={page} />;
}

function PageTitle({ page }: { page: ConfigPage }) {
  const t = useT();
  const { schema } = useConfigEditor();
  return <h2 className="mb-6 font-serif text-[1.6rem] leading-tight text-ink">{pageTitle(page, schema, t)}</h2>;
}

/** Persona, initiative, admin: one object each, edited in place. */
function SectionPage({ page }: { page: ConfigPage }) {
  const { schema, problems } = useConfigEditor();
  return (
    <>
      <PageTitle page={page} />
      <div className="grid gap-6">
        {page.keys.map((key) => {
          const section = schema.sections[key];
          if (!section) return null;
          // `data_dir` is a top-level value: its schema wraps it as the one property of an object
          const path: Path = key === "data_dir" ? [] : [key];
          const stray = problemsUnder(problems, [key]).filter((p) => p.path.length === 1 && key !== "data_dir");
          return (
            <Panel key={key}>
              <ObjectFields schema={section} root={section} path={path} />
              <Problems problems={stray} />
            </Panel>
          );
        })}
      </div>
    </>
  );
}

// -- the household ----------------------------------------------------------------------------------

function HouseholdPage({ page }: { page: ConfigPage }) {
  const t = useT();
  const { schema, draft, set, problems } = useConfigEditor();
  const person = schema.sections.household ?? {};
  const people = Array.isArray(draft.household) ? (draft.household as Record<string, unknown>[]) : [];
  const [editing, setEditing] = useState<{ index: number; adding: boolean } | null>(null);
  const add = () => {
    set(["household"], [...people, { id: "", name: "" }]);
    setEditing({ index: people.length, adding: true });
  };
  const label = (p: Record<string, unknown>, i: number) => String(p.name || p.id || t("cfg-item-n", { n: i + 1 }));
  return (
    <>
      <PageTitle page={page} />
      <Section
        title={t("cfg-people")}
        count={people.length}
        aside={
          <Button variant="outline" size="sm" onClick={add}>
            <Plus /> {t("cfg-add-person")}
          </Button>
        }
      >
        {people.length ? (
          <ul className="grid gap-2">
            {people.map((p, index) => {
              const trouble = problemsUnder(problems, ["household", index]);
              const accounts = Array.isArray(p.accounts) ? (p.accounts as string[]) : [];
              return (
                <ItemCard
                  // biome-ignore lint/suspicious/noArrayIndexKey: a person's position is its place in the file
                  key={index}
                  title={label(p, index)}
                  subtitle={String(p.id ?? "")}
                  detail={accounts.join(" · ")}
                  problems={trouble.length}
                  index={index}
                  count={people.length}
                  onEdit={() => setEditing({ index, adding: false })}
                  onMove={(by) => set(["household"], move(people, index, by))}
                  onRemove={async () =>
                    set(
                      ["household"],
                      people.filter((_, i) => i !== index),
                    )
                  }
                  removeTitle={t("cfg-remove-person-title", { name: label(p, index) })}
                  removeText={t("cfg-remove-person-text")}
                />
              );
            })}
          </ul>
        ) : (
          <Empty>{t("cfg-people-empty")}</Empty>
        )}
      </Section>
      {editing ? (
        <ItemSheet
          key={editing.index}
          title={editing.adding ? t("cfg-add-person") : label(people[editing.index] ?? {}, editing.index)}
          adding={editing.adding}
          onClose={() => setEditing(null)}
          onCancelAdd={() => {
            set(
              ["household"],
              people.filter((_, i) => i !== editing.index),
            );
            setEditing(null);
          }}
        >
          <ObjectFields schema={person} root={person} path={["household", editing.index]} />
        </ItemSheet>
      ) : null}
    </>
  );
}

// -- components (model, channels, tools…) ---------------------------------------------------------

/** The components of a slot, then the sections that choose among them (the models, then who uses which). */
function SlotsPage({ page }: { page: ConfigPage }) {
  const { schema, problems } = useConfigEditor();
  return (
    <>
      {page.keys.map((key) => {
        const slot = schema.slots[key];
        const section = schema.sections[key];
        if (slot?.shape === "named") return <NamedSlot key={key} slotKey={key} slot={slot} />;
        if (slot?.shape === "list") return <ManySlot key={key} slotKey={key} slot={slot} />;
        if (slot) return <OneSlot key={key} slotKey={key} slot={slot} main={key === page.keys[0]} />;
        if (!section) return null;
        return (
          <Section key={key} title={schema.section_titles[key] ?? key} id={`section-${key}`}>
            <Panel>
              <ObjectFields schema={section} root={section} path={[key]} />
              <Problems problems={problemsUnder(problems, [key]).filter((p) => p.path.length === 1)} />
            </Panel>
          </Section>
        );
      })}
    </>
  );
}

const SUMMARY = ["room", "model", "url", "base_url", "description"];

function summary(entry: Record<string, unknown>): string {
  return SUMMARY.map((k) => entry[k])
    .filter((v): v is string => typeof v === "string" && v !== "" && !v.includes("${"))
    .slice(0, 2)
    .join(" · ");
}

/** A slot that takes one component (the model, presence): shown and edited in place. */
function OneSlot({ slotKey, slot, main }: { slotKey: string; slot: ConfigSlot; main: boolean }) {
  const t = useT();
  const { draft, set, problems } = useConfigEditor();
  const entry = getAt(draft, [slotKey]);
  const kind = isRecord(entry) ? String(entry.kind ?? "") : "";
  const schema = slot.kinds[kind];
  const kinds = Object.keys(slot.kinds);
  const trouble = problemsUnder(problems, [slotKey]);
  return (
    <Section
      title={slot.title}
      id={`slot-${slotKey}`}
      aside={
        isRecord(entry) && !slot.required ? (
          <Confirm
            trigger={
              <Button variant="ghost" size="sm">
                <Trash2 /> {t("cfg-remove")}
              </Button>
            }
            title={t("cfg-remove-title", { name: kindTitle(kind) })}
            confirm={t("cfg-remove")}
            onConfirm={async () => set([slotKey], undefined)}
          >
            {t("cfg-remove-text")}
          </Confirm>
        ) : null
      }
    >
      {isRecord(entry) ? (
        <Panel marked={main}>
          <div className="mb-5 flex items-center gap-2.5">
            <KindMark kind={kind} className="size-5 text-ink" label={false} />
            <p className="font-serif text-lg text-ink">{kindTitle(kind)}</p>
            <span className="text-[0.85rem] text-ink-faint">{kind}</span>
          </div>
          {schema ? (
            <ObjectFields schema={schema} root={schema} path={[slotKey]} />
          ) : (
            <p className="text-sm text-brick">{t("cfg-kind-missing", { kind })}</p>
          )}
          <Problems problems={trouble.filter((p) => p.path.length <= 1)} />
        </Panel>
      ) : kinds.length ? (
        <Empty
          hint={slot.required ? t("cfg-slot-required") : t("cfg-slot-optional")}
          action={
            <KindPicker
              slot={slot}
              onPick={(k) => set([slotKey], { kind: k })}
              trigger={
                <Button variant="outline" size="sm">
                  <Plus /> {t("cfg-choose-kind")}
                </Button>
              }
            />
          }
        >
          {t("cfg-slot-unset")}
        </Empty>
      ) : (
        <Empty hint={t("cfg-no-plugin-hint")}>{t("cfg-no-plugin")}</Empty>
      )}
      {!isRecord(entry) ? <Problems problems={trouble} /> : null}
    </Section>
  );
}

/** A slot that takes a list (channels, tools…): cards, each edited in a sheet. */
function ManySlot({ slotKey, slot }: { slotKey: string; slot: ConfigSlot }) {
  const t = useT();
  const { draft, set, problems } = useConfigEditor();
  const entries = Array.isArray(draft[slotKey]) ? (draft[slotKey] as Record<string, unknown>[]) : [];
  const [editing, setEditing] = useState<{ index: number; adding: boolean } | null>(null);
  const kinds = Object.keys(slot.kinds);
  const write = (next: Record<string, unknown>[]) => set([slotKey], next.length || slot.required ? next : undefined);
  const nameOf = (e: Record<string, unknown>) => String(e.name || kindTitle(String(e.kind ?? "")));
  const current = editing ? entries[editing.index] : undefined;
  const schema = current ? slot.kinds[String(current.kind)] : undefined;
  const stray = problemsUnder(problems, [slotKey]).filter((p) => p.path.length === 1);
  return (
    <Section
      title={slot.title}
      count={entries.length}
      id={`slot-${slotKey}`}
      aside={
        kinds.length ? (
          <KindPicker
            slot={slot}
            onPick={(kind) => {
              write([...entries, { kind }]);
              setEditing({ index: entries.length, adding: true });
            }}
            trigger={
              <Button variant="outline" size="sm">
                <Plus /> {t("cfg-add-component")}
              </Button>
            }
          />
        ) : null
      }
    >
      {entries.length ? (
        <ul className="grid gap-2">
          {entries.map((entry, index) => {
            const kind = String(entry.kind ?? "");
            return (
              <ItemCard
                // biome-ignore lint/suspicious/noArrayIndexKey: a component's position is its place in the file
                key={index}
                mark={markOf(kind, entry, slot.kinds[kind])}
                title={nameOf(entry)}
                subtitle={kind}
                detail={summary(entry)}
                problems={problemsUnder(problems, [slotKey, index]).length}
                missing={!slot.kinds[kind]}
                index={index}
                count={entries.length}
                onEdit={() => setEditing({ index, adding: false })}
                onMove={(by) => write(move(entries, index, by))}
                onRemove={async () => write(entries.filter((_, i) => i !== index))}
                removeTitle={t("cfg-remove-title", { name: nameOf(entry) })}
                removeText={t("cfg-remove-text")}
              />
            );
          })}
        </ul>
      ) : kinds.length ? (
        <Empty hint={slot.required ? t("cfg-slot-required") : t("cfg-slot-optional")}>{t("cfg-slot-none")}</Empty>
      ) : (
        <Empty hint={t("cfg-no-plugin-hint")}>{t("cfg-no-plugin")}</Empty>
      )}
      <Problems problems={stray} />
      {editing && current ? (
        <ItemSheet
          key={editing.index}
          title={editing.adding ? t("cfg-add-kind", { kind: kindTitle(String(current.kind)) }) : nameOf(current)}
          mark={String(current.kind)}
          adding={editing.adding}
          onClose={() => setEditing(null)}
          onCancelAdd={() => {
            write(entries.filter((_, i) => i !== editing.index));
            setEditing(null);
          }}
        >
          {schema ? (
            <ObjectFields schema={schema} root={schema} path={[slotKey, editing.index]} />
          ) : (
            <p className="text-sm text-brick">{t("cfg-kind-missing", { kind: String(current.kind) })}</p>
          )}
        </ItemSheet>
      ) : null}
    </Section>
  );
}

/** A slot whose components have names other settings use (the models): cards by name, each edited in a sheet. */
function NamedSlot({ slotKey, slot }: { slotKey: string; slot: ConfigSlot }) {
  const t = useT();
  const { schema: config, draft, set, replace, problems } = useConfigEditor();
  const named = isRecord(draft[slotKey]) ? (draft[slotKey] as Record<string, Record<string, unknown>>) : {};
  const names = Object.keys(named);
  const [editing, setEditing] = useState<{ name: string; adding: boolean } | null>(null);
  const kinds = Object.keys(slot.kinds);
  const write = (next: Record<string, unknown>) => set([slotKey], next);
  const current = editing ? named[editing.name] : undefined;
  const schema = current ? slot.kinds[String(current.kind)] : undefined;
  const stray = problemsUnder(problems, [slotKey]).filter((p) => p.path.length === 1);
  const without = (name: string) => Object.fromEntries(Object.entries(named).filter(([k]) => k !== name));
  return (
    <Section
      title={slot.title}
      count={names.length}
      id={`slot-${slotKey}`}
      aside={
        kinds.length ? (
          <KindPicker
            slot={slot}
            onPick={(kind) => {
              const name = freeName(kind, names);
              write({ ...named, [name]: { kind } });
              setEditing({ name, adding: true });
            }}
            trigger={
              <Button variant="outline" size="sm">
                <Plus /> {t("cfg-add-component")}
              </Button>
            }
          />
        ) : null
      }
    >
      {names.length ? (
        <ul className="grid gap-2">
          {Object.entries(named).map(([name, entry]) => {
            const kind = String(entry.kind ?? "");
            return (
              <ItemCard
                key={name}
                mark={markOf(kind, entry, slot.kinds[kind])}
                title={name}
                subtitle={kindTitle(kind)}
                detail={summary(entry)}
                problems={problemsUnder(problems, [slotKey, name]).length}
                missing={!slot.kinds[kind]}
                onEdit={() => setEditing({ name, adding: false })}
                onRemove={async () => write(without(name))}
                removeTitle={t("cfg-remove-title", { name })}
                removeText={t("cfg-remove-text")}
              />
            );
          })}
        </ul>
      ) : kinds.length ? (
        <Empty hint={slot.required ? t("cfg-slot-required") : t("cfg-slot-optional")}>{t("cfg-slot-none")}</Empty>
      ) : (
        <Empty hint={t("cfg-no-plugin-hint")}>{t("cfg-no-plugin")}</Empty>
      )}
      <Problems problems={stray} />
      {editing && current ? (
        <ItemSheet
          title={editing.adding ? t("cfg-add-kind", { kind: kindTitle(String(current.kind)) }) : editing.name}
          mark={String(current.kind)}
          adding={editing.adding}
          onClose={() => setEditing(null)}
          onCancelAdd={() => {
            write(without(editing.name));
            setEditing(null);
          }}
        >
          <NameField
            name={editing.name}
            taken={names.filter((n) => n !== editing.name)}
            onRename={(to) => {
              replace(renamed(draft, config.sections, slotKey, editing.name, to));
              setEditing({ ...editing, name: to });
            }}
          />
          {schema ? (
            <ObjectFields schema={schema} root={schema} path={[slotKey, editing.name]} />
          ) : (
            <p className="text-sm text-brick">{t("cfg-kind-missing", { kind: String(current.kind) })}</p>
          )}
        </ItemSheet>
      ) : null}
    </Section>
  );
}

/** A named component's name: renamed once it is a free, valid one (on leaving the field or Enter). */
function NameField({ name, taken, onRename }: { name: string; taken: string[]; onRename: (to: string) => void }) {
  const t = useT();
  const id = useId();
  const [text, setText] = useState(name);
  const trimmed = text.trim();
  const problem = !NAME.test(trimmed) ? t("cfg-name-invalid") : taken.includes(trimmed) ? t("cfg-name-taken") : null;
  const commit = () => {
    if (!problem && trimmed !== name) onRename(trimmed);
  };
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{t("cfg-name")}</Label>
      <Input
        id={id}
        value={text}
        spellCheck={false}
        className="font-mono text-[0.82rem] sm:max-w-72"
        aria-invalid={problem ? true : undefined}
        aria-describedby={`${id}-help`}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
      />
      <p id={`${id}-help`} className={cn("text-[0.85rem]", problem ? "text-brick" : "text-ink-muted")}>
        {problem ?? t("cfg-name-help")}
      </p>
    </div>
  );
}

/** Choosing what to add: every installed plugin of the slot, with its mark. */
function KindPicker({
  slot,
  onPick,
  trigger,
}: {
  slot: ConfigSlot;
  onPick: (kind: string) => void;
  trigger: ReactElement;
}) {
  const t = useT();
  return (
    <FormDialog trigger={trigger} title={t("cfg-pick-title", { slot: slot.title })} description={t("cfg-pick-text")}>
      {(close) => (
        <ul className="grid gap-1.5">
          {Object.entries(slot.kinds).map(([kind, schema]) => (
            <li key={kind}>
              <button
                type="button"
                onClick={() => {
                  close();
                  onPick(kind);
                }}
                className="flex w-full items-center gap-3 rounded-md border border-rule bg-paper-raised px-3 py-2.5 text-left hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ember"
              >
                <KindMark kind={kind} className="size-5 text-ink" label={false} />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm text-ink">{kindTitle(kind)}</span>
                  <span className="block text-[0.85rem] text-ink-faint">
                    {kind} · {t("cfg-required-fields", { count: requiredCount(schema) })}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </FormDialog>
  );
}

const requiredCount = (schema: JsonSchema) => (schema.required ?? []).filter((r) => r !== "kind").length;

function ItemCard({
  mark,
  title,
  subtitle,
  detail,
  problems,
  missing = false,
  index,
  count,
  onEdit,
  onMove,
  onRemove,
  removeTitle,
  removeText,
}: {
  mark?: string;
  title: string;
  subtitle: string;
  detail: string;
  problems: number;
  missing?: boolean;
  /** Its place among the others, for the arrows that reorder them; none when the order is not the file's. */
  index?: number;
  count?: number;
  onEdit: () => void;
  onMove?: (by: -1 | 1) => void;
  onRemove: () => Promise<void>;
  removeTitle: string;
  removeText: string;
}) {
  const t = useT();
  return (
    <li
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border border-rule bg-paper-raised px-4 py-3",
        problems > 0 && "border-brick/50",
      )}
    >
      {mark ? <KindMark kind={mark} className="size-5 text-ink" label={false} /> : null}
      <button type="button" onClick={onEdit} className="group min-w-0 flex-1 text-left">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-[0.95rem] text-ink group-hover:underline group-hover:underline-offset-4">{title}</span>
          <span className="text-[0.85rem] text-ink-faint">{subtitle}</span>
        </span>
        {detail ? <span className="mt-0.5 block truncate text-[0.85rem] text-ink-muted">{detail}</span> : null}
      </button>
      {problems || missing ? (
        <span className="inline-flex items-center gap-1 text-[0.85rem] text-brick">
          <CircleAlert className="size-3.5" aria-hidden="true" />
          {missing ? t("cfg-kind-missing-short") : t("cfg-problems", { count: problems })}
        </span>
      ) : null}
      <span className="flex items-center">
        <Button variant="ghost" size="icon-sm" onClick={onEdit} aria-label={t("cfg-edit-item", { item: title })}>
          <Pencil />
        </Button>
        {onMove && index !== undefined && count !== undefined ? (
          <>
            <Button
              variant="ghost"
              size="icon-sm"
              disabled={index === 0}
              onClick={() => onMove(-1)}
              aria-label={t("cfg-move-up", { item: title })}
            >
              <ArrowUp />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              disabled={index === count - 1}
              onClick={() => onMove(1)}
              aria-label={t("cfg-move-down", { item: title })}
            >
              <ArrowDown />
            </Button>
          </>
        ) : null}
        <Confirm
          trigger={
            <Button variant="ghost" size="icon-sm" aria-label={t("cfg-remove-item", { item: title })}>
              <Trash2 />
            </Button>
          }
          title={removeTitle}
          confirm={t("cfg-remove")}
          onConfirm={onRemove}
        >
          {removeText}
        </Confirm>
      </span>
    </li>
  );
}

/** A component's or a person's form, in a sheet: edits go straight into the draft. */
function ItemSheet({
  title,
  mark,
  adding,
  onClose,
  onCancelAdd,
  children,
}: {
  title: string;
  mark?: string;
  adding: boolean;
  onClose: () => void;
  onCancelAdd: () => void;
  children: ReactNode;
}) {
  const t = useT();
  return (
    <FormSheet
      open
      onOpenChange={(open) => !open && onClose()}
      title={title}
      description={
        mark ? (
          <span className="inline-flex items-center gap-1.5 text-[0.85rem]">
            <KindMark kind={mark} className="size-3.5" label={false} /> {mark}
          </span>
        ) : undefined
      }
    >
      {() => (
        <div className="grid gap-6 pt-5">
          {children}
          <FormActions hint={t("cfg-sheet-note")}>
            {adding ? (
              <Button variant="ghost" onClick={onCancelAdd}>
                {t("cfg-cancel-add")}
              </Button>
            ) : null}
            <Button onClick={onClose}>{t("cfg-done")}</Button>
          </FormActions>
        </div>
      )}
    </FormSheet>
  );
}
