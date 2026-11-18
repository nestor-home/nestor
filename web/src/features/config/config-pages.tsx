/**
 * A page of the configuration: what the file holds as cards and rows a person reads, each opening its
 * form in a sheet. Every edit goes into the one draft; nothing is written before "Save".
 */
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react";
import { type ReactElement, type ReactNode, useId, useRef, useState } from "react";
import type { ModelType } from "@/api";
import { modelTypeValues } from "@/api/schema.gen";
import { CardHead } from "@/components/card";
import { Confirm } from "@/components/confirm";
import { FormActions } from "@/components/form-actions";
import { Pebble, ServiceTile } from "@/components/marks";
import { FormDialog, FormSheet } from "@/components/overlay-form";
import { Fact, Facts, Panel, Section } from "@/components/page";
import { Empty } from "@/components/states";
import { Status, Tag } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { KindMark, KindName, kindName } from "@/lib/brands";
import { MODEL_TYPE_ICON, roleIcon } from "@/lib/icons";
import { modelTypeHint } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { ConfigFrame } from "./config-layout";
import { useConfigEditor } from "./editor";
import { ObjectFields, Problems } from "./fields";
import {
  entryOf,
  fieldsOf,
  freeName,
  getAt,
  type JsonSchema,
  move,
  NAME,
  type Path,
  problemsUnder,
  providerOf,
  renamed,
  resolve,
  type Slot,
  titleOf,
} from "./schema";
import { type ConfigPage, pageTitle } from "./sections";
import { type Component, componentsOf, defaultShown, peopleOf, rolesOf, valueText } from "./summary";

const CARDS = "grid gap-3 sm:grid-cols-2";

/** A type of model in a word, where its mark stands beside it. */
const modelTypeShort = (type: ModelType) => tr("cfg-model-type", { type });

export function ConfigPageView({ page }: { page: ConfigPage }) {
  const t = useT();
  const { schema } = useConfigEditor();
  return (
    <ConfigFrame title={pageTitle(page, schema, t)} about={page.about ? t(page.about) : undefined}>
      {page.kind === "household" ? (
        <Household />
      ) : (
        page.keys.map((key) => {
          const slot = schema.slots[key];
          if (slot?.shape === "named") return <NamedSlot key={key} slotKey={key} slot={slot} />;
          if (slot?.shape === "list") return <ManySlot key={key} slotKey={key} slot={slot} />;
          if (slot) return <OneSlot key={key} slotKey={key} slot={slot} />;
          const section = schema.sections[key];
          if (!section) return null;
          const title = page.keys.length > 1 ? (schema.section_titles[key] ?? key) : t("cfg-settings");
          return <Settings key={key} sectionKey={key} section={section} title={title} />;
        })
      )}
    </ConfigFrame>
  );
}

// -- a section of settings (persona, initiative, who uses which model…) ---------------------------

/** One object of the file: each setting and what it is now, changed in a sheet. */
function Settings({ sectionKey, section, title }: { sectionKey: string; section: JsonSchema; title: string }) {
  const t = useT();
  const { schema, draft, problems } = useConfigEditor();
  const [open, setOpen] = useState(false);
  // `data_dir` is a top-level value: its schema wraps it as the one property of an object
  const path: Path = sectionKey === "data_dir" ? [] : [sectionKey];
  const name = schema.section_titles[sectionKey] ?? sectionKey;
  const { plain, advanced } = fieldsOf(resolve(section, section).schema);
  const set = advanced.filter(([field]) => getAt(draft, [...path, field]) !== undefined);
  const rows = plain.length || set.length ? [...plain, ...set] : advanced;
  const stray = problemsUnder(problems, [sectionKey]).filter((p) => p.path.length === 1 && path.length === 1);
  return (
    <Section
      title={title}
      id={`section-${sectionKey}`}
      aside={
        <Button
          variant="outline"
          size="sm"
          onClick={() => setOpen(true)}
          aria-label={t("cfg-edit-item", { item: name })}
        >
          <Pencil /> {t("cfg-edit")}
        </Button>
      }
    >
      <Panel>
        <Facts>
          {rows.map(([field, node]) => {
            const value = valueText(node, getAt(draft, [...path, field]));
            const fallback = defaultShown(node, section);
            return (
              <Fact key={field} term={titleOf(node, field)} className="min-w-0">
                {value !== null ? (
                  <span className="line-clamp-3 text-ink">{value}</span>
                ) : (
                  <span className="text-ink-faint">
                    {fallback ? t("cfg-default", { value: fallback }) : t("cfg-unset")}
                  </span>
                )}
                <Problems problems={problemsUnder(problems, [...path, field])} label={titleOf(node, field)} />
              </Fact>
            );
          })}
        </Facts>
      </Panel>
      <Problems problems={stray} />
      <FormSheet open={open} onOpenChange={setOpen} title={name}>
        {(close) => (
          <div className="grid gap-6 pt-5">
            <ObjectFields schema={section} root={section} path={path} />
            <Problems problems={stray} />
            <FormActions hint={t("cfg-sheet-note")}>
              <Button onClick={close}>{t("cfg-done")}</Button>
            </FormActions>
          </div>
        )}
      </FormSheet>
    </Section>
  );
}

// -- the household ----------------------------------------------------------------------------------

function Household() {
  const t = useT();
  const { schema, draft, set, problems } = useConfigEditor();
  const person = schema.sections.household ?? {};
  const people = peopleOf(draft);
  const [editing, setEditing] = useState<{ index: number; adding: boolean } | null>(null);
  const write = (next: Record<string, unknown>[]) => set(["household"], next);
  const without = (index: number) => people.filter((_, i) => i !== index);
  const label = (p: Record<string, unknown>, i: number) => String(p.name || p.id || t("cfg-item-n", { n: i + 1 }));
  const current = editing ? people[editing.index] : undefined;
  return (
    <Section
      title={t("cfg-people")}
      count={people.length}
      aside={
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            write([...people, { id: "", name: "" }]);
            setEditing({ index: people.length, adding: true });
          }}
        >
          <Plus /> {t("cfg-add-person")}
        </Button>
      }
    >
      {people.length ? (
        <ul className={CARDS}>
          {people.map((p, index) => {
            const accounts = Array.isArray(p.accounts) ? p.accounts.map(String) : [];
            return (
              <Card
                // biome-ignore lint/suspicious/noArrayIndexKey: a person's position is its place in the file
                key={index}
                mark={<Pebble name={label(p, index)} size="lg" />}
                title={label(p, index)}
                line={accounts.length ? accounts.join(" · ") : t("cfg-person-no-account")}
                marks={accounts}
                problems={problemsUnder(problems, ["household", index]).length}
                onOpen={() => setEditing({ index, adding: false })}
              />
            );
          })}
        </ul>
      ) : (
        <Empty>{t("cfg-people-empty")}</Empty>
      )}
      {editing && current ? (
        <ItemSheet
          title={editing.adding ? t("cfg-add-person") : label(current, editing.index)}
          adding={editing.adding}
          onClose={() => setEditing(null)}
          onRemove={() => {
            write(without(editing.index));
            setEditing(null);
          }}
          removeTitle={t("cfg-remove-person-title", { name: label(current, editing.index) })}
          removeText={t("cfg-remove-person-text")}
          order={{
            item: label(current, editing.index),
            index: editing.index,
            count: people.length,
            move: (by) => {
              write(move(people, editing.index, by));
              setEditing({ ...editing, index: editing.index + by });
            },
          }}
        >
          <ObjectFields schema={person} root={person} path={["household", editing.index]} />
        </ItemSheet>
      ) : null}
    </Section>
  );
}

// -- components (models, channels, tools…) ----------------------------------------------------------

const SUMMARY = ["room", "model", "url", "base_url", "description"];

function summary(entry: Record<string, unknown>): string {
  return SUMMARY.map((k) => entry[k])
    .filter((v): v is string => typeof v === "string" && v !== "" && !v.includes("${"))
    .slice(0, 2)
    .join(" · ");
}

function ComponentCard({
  slot,
  component: c,
  title = c.name,
  line,
  type,
  roles,
  problems,
  onOpen,
}: {
  slot: Slot;
  component: Component;
  title?: string;
  line: string;
  /** For a model: what kind of model it is. */
  type?: ModelType;
  /** For a model: the roles it holds. */
  roles?: { field: string; title: string }[];
  problems: number;
  onOpen: () => void;
}) {
  return (
    <Card
      mark={<ServiceTile kind={c.mark} />}
      title={title}
      line={line}
      detail={summary(c.entry)}
      type={type}
      roles={roles}
      problems={problems}
      missing={!slot.kinds[c.plugin]}
      onOpen={onOpen}
    />
  );
}

/** Nothing in a slot yet: whether one is needed, and the way to add one when a plugin is installed. */
function NoComponent({ slot, action }: { slot: Slot; action?: ReactNode }) {
  const t = useT();
  if (!Object.keys(slot.kinds).length) return <Empty hint={t("cfg-no-plugin-hint")}>{t("cfg-no-plugin")}</Empty>;
  return (
    <Empty hint={slot.required ? t("cfg-slot-required") : t("cfg-slot-optional")} action={action}>
      {t("cfg-slot-none")}
    </Empty>
  );
}

function AddButton({ slotKey, slot, onPick }: { slotKey: string; slot: Slot; onPick: (kind: string) => void }) {
  const t = useT();
  if (!Object.keys(slot.kinds).length) return null;
  return (
    <KindPicker
      slotKey={slotKey}
      slot={slot}
      onPick={onPick}
      trigger={
        <Button variant="outline" size="sm">
          <Plus /> {t("cfg-add-one", { slot: slotKey, title: slot.title })}
        </Button>
      }
    />
  );
}

function Fields({ slot, plugin, path }: { slot: Slot; plugin: string; path: Path }) {
  const t = useT();
  const schema = slot.kinds[plugin];
  if (!schema) return <p className="text-meta text-brick">{t("cfg-kind-missing", { kind: plugin })}</p>;
  return <ObjectFields schema={schema} root={schema} path={path} />;
}

/** A slot that takes one component (the home system): its card, or the choice of what to set up. */
function OneSlot({ slotKey, slot }: { slotKey: string; slot: Slot }) {
  const t = useT();
  const { draft, set, problems } = useConfigEditor();
  const [editing, setEditing] = useState<{ adding: boolean } | null>(null);
  const current = componentsOf(slot, slotKey, draft)[0];
  const trouble = problemsUnder(problems, [slotKey]);
  const remove = () => {
    set([slotKey], undefined);
    setEditing(null);
  };
  return (
    <Section title={slot.title} id={`slot-${slotKey}`}>
      {current ? (
        <ul className={CARDS}>
          <ComponentCard
            slot={slot}
            component={current}
            line={current.plugin}
            problems={trouble.length}
            onOpen={() => setEditing({ adding: false })}
          />
        </ul>
      ) : (
        <NoComponent
          slot={slot}
          action={
            <AddButton
              slotKey={slotKey}
              slot={slot}
              onPick={(kind) => {
                set([slotKey], entryOf(slot, kind));
                setEditing({ adding: true });
              }}
            />
          }
        />
      )}
      {current ? null : <Problems problems={trouble} />}
      {editing && current ? (
        <ItemSheet
          title={editing.adding ? t("cfg-add-kind", { kind: current.name }) : current.name}
          mark={current.provider}
          adding={editing.adding}
          onClose={() => setEditing(null)}
          onRemove={slot.required && !editing.adding ? undefined : remove}
          removeTitle={t("cfg-remove-title", { name: current.name })}
          removeText={t("cfg-remove-text")}
        >
          <Fields slot={slot} plugin={current.plugin} path={[slotKey]} />
          <Problems problems={trouble.filter((p) => p.path.length <= 1)} />
        </ItemSheet>
      ) : null}
    </Section>
  );
}

/** A slot that takes a list (channels, tools…): cards, each edited in a sheet. */
function ManySlot({ slotKey, slot }: { slotKey: string; slot: Slot }) {
  const t = useT();
  const { draft, set, problems } = useConfigEditor();
  const components = componentsOf(slot, slotKey, draft);
  const entries = components.map((c) => c.entry);
  const [editing, setEditing] = useState<{ index: number; adding: boolean } | null>(null);
  const write = (next: Record<string, unknown>[]) => set([slotKey], next.length || slot.required ? next : undefined);
  const current = editing ? components[editing.index] : undefined;
  const stray = problemsUnder(problems, [slotKey]).filter((p) => p.path.length === 1);
  return (
    <Section
      title={slot.title}
      count={components.length}
      id={`slot-${slotKey}`}
      aside={
        <AddButton
          slotKey={slotKey}
          slot={slot}
          onPick={(kind) => {
            write([...entries, entryOf(slot, kind)]);
            setEditing({ index: entries.length, adding: true });
          }}
        />
      }
    >
      {components.length ? (
        <ul className={CARDS}>
          {components.map((c, index) => (
            <ComponentCard
              // biome-ignore lint/suspicious/noArrayIndexKey: a component's position is its place in the file
              key={index}
              slot={slot}
              component={c}
              line={c.name === kindName(c.provider) ? c.plugin : `${kindName(c.provider)} · ${c.plugin}`}
              problems={problemsUnder(problems, [slotKey, index]).length}
              onOpen={() => setEditing({ index, adding: false })}
            />
          ))}
        </ul>
      ) : (
        <NoComponent slot={slot} />
      )}
      <Problems problems={stray} />
      {editing && current ? (
        <ItemSheet
          title={editing.adding ? t("cfg-add-kind", { kind: kindName(current.provider) }) : current.name}
          mark={current.provider}
          adding={editing.adding}
          onClose={() => setEditing(null)}
          onRemove={() => {
            write(entries.filter((_, i) => i !== editing.index));
            setEditing(null);
          }}
          removeTitle={t("cfg-remove-title", { name: current.name })}
          removeText={t("cfg-remove-text")}
          order={{
            item: current.name,
            index: editing.index,
            count: entries.length,
            move: (by) => {
              write(move(entries, editing.index, by));
              setEditing({ ...editing, index: editing.index + by });
            },
          }}
        >
          <Fields slot={slot} plugin={current.plugin} path={[slotKey, editing.index]} />
        </ItemSheet>
      ) : null}
    </Section>
  );
}

/** A slot whose components have names other settings use (the models): cards by name, each edited in a sheet. */
function NamedSlot({ slotKey, slot }: { slotKey: string; slot: Slot }) {
  const t = useT();
  const { schema: config, draft, set, replace, problems } = useConfigEditor();
  const components = componentsOf(slot, slotKey, draft);
  const names = components.map((c) => c.name);
  const [editing, setEditing] = useState<{ name: string; adding: boolean } | null>(null);
  const current = editing ? components.find((c) => c.name === editing.name) : undefined;
  const stray = problemsUnder(problems, [slotKey]).filter((p) => p.path.length === 1);
  const named = (list: Component[]) => Object.fromEntries(list.map((c) => [c.name, c.entry]));
  const without = (name: string) => named(components.filter((c) => c.name !== name));
  return (
    <Section
      title={slot.title}
      count={names.length}
      id={`slot-${slotKey}`}
      aside={
        <AddButton
          slotKey={slotKey}
          slot={slot}
          onPick={(kind) => {
            const name = freeName(providerOf(slot, kind), names);
            set([slotKey], { ...named(components), [name]: entryOf(slot, kind) });
            setEditing({ name, adding: true });
          }}
        />
      }
    >
      {components.length ? (
        <ul className={CARDS}>
          {components.map((c) => {
            const type = slot.model_types[c.plugin];
            return (
              <ComponentCard
                key={c.name}
                slot={slot}
                component={c}
                line={kindName(c.provider)}
                type={type}
                roles={rolesOf(config, draft, slotKey, c.name)}
                problems={problemsUnder(problems, [slotKey, c.name]).length}
                onOpen={() => setEditing({ name: c.name, adding: false })}
              />
            );
          })}
        </ul>
      ) : (
        <NoComponent slot={slot} />
      )}
      <Problems problems={stray} />
      {editing && current ? (
        <ItemSheet
          title={editing.adding ? t("cfg-add-kind", { kind: kindName(current.provider) }) : editing.name}
          mark={current.provider}
          adding={editing.adding}
          onClose={() => setEditing(null)}
          onRemove={() => {
            set([slotKey], without(editing.name));
            setEditing(null);
          }}
          removeTitle={t("cfg-remove-title", { name: editing.name })}
          removeText={t("cfg-remove-text")}
        >
          <NameField
            name={editing.name}
            taken={names.filter((n) => n !== editing.name)}
            onRename={(to) => {
              replace(renamed(draft, config.sections, slotKey, editing.name, to));
              setEditing({ ...editing, name: to });
            }}
          />
          <Fields slot={slot} plugin={current.plugin} path={[slotKey, editing.name]} />
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
        className="font-mono text-meta sm:max-w-72"
        aria-invalid={problem ? true : undefined}
        aria-describedby={`${id}-help`}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
      />
      <p id={`${id}-help`} className={cn("text-meta", problem ? "text-brick" : "text-ink-muted")}>
        {problem ?? t("cfg-name-help")}
      </p>
    </div>
  );
}

/**
 * Choosing what to add: for models, the type first (what it will do, with its mark), then who provides it; for
 * anything else, who provides it. One click picks, and its form opens.
 */
function KindPicker({
  slotKey,
  slot,
  onPick,
  trigger,
}: {
  slotKey: string;
  slot: Slot;
  onPick: (kind: string) => void;
  trigger: ReactElement;
}) {
  const t = useT();
  const kinds = Object.keys(slot.kinds);
  const types = modelTypeValues.filter((type) => kinds.some((k) => slot.model_types[k] === type));
  const [type, setType] = useState<ModelType | undefined>(types[0]);
  const shown = types.length ? kinds.filter((k) => slot.model_types[k] === type) : kinds;
  return (
    <FormDialog
      trigger={trigger}
      title={t("cfg-add-one", { slot: slotKey, title: slot.title })}
      description={t(types.length ? "cfg-pick-model" : "cfg-pick-text")}
      wide
    >
      {(close) => (
        <div className={cn("grid gap-5", types.length && "md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]")}>
          {types.length ? (
            <ul
              aria-label={t("cfg-pick-type")}
              className="flex gap-2 overflow-x-auto pb-1 md:grid md:content-start md:gap-1 md:overflow-visible md:pb-0"
            >
              {types.map((option) => {
                const Icon = MODEL_TYPE_ICON[option];
                const chosen = option === type;
                return (
                  <li key={option} className="shrink-0">
                    <button
                      type="button"
                      aria-pressed={chosen}
                      onClick={() => setType(option)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-xl p-2 pr-3 text-left transition-colors",
                        chosen ? "bg-paper-sunken" : "hover:bg-paper-sunken/60",
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          "grid size-9 shrink-0 place-items-center rounded-lg",
                          chosen ? "bg-ink text-paper" : "bg-paper-sunken text-ink-muted",
                        )}
                      >
                        <Icon className="size-4.5" />
                      </span>
                      <span className="min-w-0">
                        <span className="block text-body font-medium whitespace-nowrap text-ink">
                          {modelTypeShort(option)}
                        </span>
                        <span className="hidden text-meta leading-snug text-ink-muted md:block">
                          {modelTypeHint(option)}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : null}
          <ul aria-label={type ? modelTypeShort(type) : undefined} className="grid content-start gap-2.5">
            {shown.map((kind) => {
              const provider = providerOf(slot, kind);
              return (
                <li key={kind}>
                  <button
                    type="button"
                    onClick={() => {
                      close();
                      onPick(kind);
                    }}
                    className="surface flex h-full w-full items-center gap-3.5 p-3.5 text-left"
                  >
                    <ServiceTile kind={provider} size="lg" />
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium text-ink">{kindName(provider)}</span>
                      <span className="block text-meta text-ink-muted">
                        {t("cfg-required-fields", { count: requiredCount(slot.kinds[kind] ?? {}) })}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </FormDialog>
  );
}

/** The fields a person must fill: what picks the plugin is set already. */
const requiredCount = (schema: JsonSchema) =>
  (schema.required ?? []).filter((r) => schema.properties?.[r]?.const === undefined).length;

// -- the pieces -------------------------------------------------------------------------------------

/** One thing the file holds (a model, a channel, a person): its mark, its name, what it is, and where it stands. */
function Card({
  mark,
  title,
  line,
  detail,
  type,
  roles = [],
  marks = [],
  problems,
  missing = false,
  onOpen,
}: {
  mark: ReactNode;
  title: string;
  line: string;
  detail?: string;
  type?: ModelType;
  roles?: { field: string; title: string }[];
  /** The channels a person is known on, as small marks. */
  marks?: string[];
  problems: number;
  missing?: boolean;
  onOpen: () => void;
}) {
  const t = useT();
  return (
    <li>
      <button type="button" onClick={onOpen} className="surface h-full w-full p-4 text-left">
        <CardHead
          mark={mark}
          title={title}
          line={
            <>
              <span className="block truncate">{line}</span>
              {detail ? <span className="block truncate text-meta text-ink-faint">{detail}</span> : null}
            </>
          }
          aside={
            marks.length ? (
              <span className="flex gap-1.5 text-ink-muted">
                {marks.map((m) => (
                  <KindMark key={m} kind={m} label={false} />
                ))}
              </span>
            ) : null
          }
        >
          {type || roles.length ? (
            <span className="flex flex-wrap gap-1.5">
              {type ? <Tag icon={MODEL_TYPE_ICON[type]}>{modelTypeShort(type)}</Tag> : null}
              {roles.map((role) => (
                <Tag key={role.field} icon={roleIcon(role.field)} tone="accent">
                  {role.title}
                </Tag>
              ))}
            </span>
          ) : null}
          {problems || missing ? (
            <Status tone="error">
              {missing ? t("cfg-kind-missing-short") : t("cfg-problems", { count: problems })}
            </Status>
          ) : null}
        </CardHead>
      </button>
    </li>
  );
}

/** A component's or a person's form, in a sheet: edits go straight into the draft. */
function ItemSheet({
  title,
  mark,
  adding,
  onClose,
  onRemove,
  removeTitle,
  removeText,
  order,
  children,
}: {
  title: string;
  mark?: string;
  adding: boolean;
  onClose: () => void;
  /** Takes it out of the draft and closes; none for the one component a slot requires. */
  onRemove?: () => void;
  removeTitle: string;
  removeText: string;
  /** Its place among the others, when the order is the file's. */
  order?: { item: string; index: number; count: number; move: (by: -1 | 1) => void };
  children: ReactNode;
}) {
  const t = useT();
  // its page mounts it while an item is open: it closes first, then tells the page, so it leaves as it came
  const [open, setOpen] = useState(true);
  const after = useRef(onClose);
  const leave = (then: () => void) => {
    after.current = then;
    setOpen(false);
  };
  return (
    <FormSheet
      open={open}
      // dismissing a sheet that adds is cancelling the add: only Done keeps what it adds
      onOpenChange={(next) => !next && leave(adding && onRemove ? onRemove : onClose)}
      onClosed={() => after.current()}
      title={title}
      description={mark ? <KindName kind={mark} /> : undefined}
    >
      {() => (
        <div className="grid gap-6">
          {children}
          <FormActions hint={t("cfg-sheet-note")}>
            {adding ? (
              onRemove ? (
                <Button variant="ghost" onClick={() => leave(onRemove)}>
                  {t("cfg-cancel-add")}
                </Button>
              ) : null
            ) : (
              <>
                {order && order.count > 1 ? (
                  <span className="flex items-center">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      disabled={order.index === 0}
                      onClick={() => order.move(-1)}
                      aria-label={t("cfg-move-up", { item: order.item })}
                    >
                      <ArrowUp />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      disabled={order.index === order.count - 1}
                      onClick={() => order.move(1)}
                      aria-label={t("cfg-move-down", { item: order.item })}
                    >
                      <ArrowDown />
                    </Button>
                  </span>
                ) : null}
                {onRemove ? (
                  <Confirm
                    trigger={
                      <Button variant="destructive">
                        <Trash2 /> {t("cfg-remove")}
                      </Button>
                    }
                    title={removeTitle}
                    confirm={t("cfg-remove")}
                    onConfirm={async () => leave(onRemove)}
                  >
                    {removeText}
                  </Confirm>
                ) : null}
              </>
            )}
            <Button onClick={() => leave(onClose)}>{t("cfg-done")}</Button>
          </FormActions>
        </div>
      )}
    </FormSheet>
  );
}
