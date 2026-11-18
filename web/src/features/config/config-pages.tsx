/**
 * A page of the configuration: what the file holds as cards and rows a person reads, each opening its
 * form in a sheet. Every edit goes into the one draft; nothing is written before "Save".
 */
import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from "lucide-react";
import { type ReactElement, type ReactNode, useId, useState } from "react";
import { modelTypeValues } from "@/api/schema.gen";
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
import { KindMark, kindName } from "@/lib/brands";
import { modelTypeHint, modelTypeLabel } from "@/lib/labels";
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
              <Fact key={field} term={titleOf(node, field)} className="min-w-0 [overflow-wrap:anywhere]">
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
                mark={<Pebble name={label(p, index)} className="size-10 text-[1rem]" />}
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
  tags,
  problems,
  onOpen,
}: {
  slot: Slot;
  component: Component;
  title?: string;
  line: string;
  tags?: string[];
  problems: number;
  onOpen: () => void;
}) {
  return (
    <Card
      mark={<ServiceTile kind={c.mark} />}
      title={title}
      line={line}
      detail={summary(c.entry)}
      tags={tags}
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

function AddButton({ slot, onPick }: { slot: Slot; onPick: (kind: string) => void }) {
  const t = useT();
  if (!Object.keys(slot.kinds).length) return null;
  return (
    <KindPicker
      slot={slot}
      onPick={onPick}
      trigger={
        <Button variant="outline" size="sm">
          <Plus /> {t("cfg-add-component")}
        </Button>
      }
    />
  );
}

function Fields({ slot, plugin, path }: { slot: Slot; plugin: string; path: Path }) {
  const t = useT();
  const schema = slot.kinds[plugin];
  if (!schema) return <p className="text-sm text-brick">{t("cfg-kind-missing", { kind: plugin })}</p>;
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
                line={type ? `${kindName(c.provider)} · ${modelTypeLabel(type)}` : kindName(c.provider)}
                tags={rolesOf(config, draft, slotKey, c.name)}
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

/** Choosing what to add: every installed plugin of the slot, by its mark; models grouped by what they serve. */
function KindPicker({ slot, onPick, trigger }: { slot: Slot; onPick: (kind: string) => void; trigger: ReactElement }) {
  const t = useT();
  return (
    <FormDialog
      trigger={trigger}
      title={t("cfg-pick-title", { slot: slot.title })}
      description={t("cfg-pick-text")}
      wide
    >
      {(close) => {
        const kinds = Object.keys(slot.kinds);
        const typed = modelTypeValues.map((type) => ({
          type,
          kinds: kinds.filter((k) => slot.model_types[k] === type),
        }));
        const groups = Object.keys(slot.model_types).length
          ? typed.filter((g) => g.kinds.length)
          : [{ type: null, kinds }];
        const option = (kind: string) => {
          const provider = providerOf(slot, kind);
          return (
            <li key={kind}>
              <button
                type="button"
                onClick={() => {
                  close();
                  onPick(kind);
                }}
                className="flex h-full w-full flex-col items-start gap-2.5 rounded-xl border border-rule bg-paper p-3 text-left transition-colors hover:border-ink"
              >
                <KindMark kind={provider} className="size-6 text-ink" label={false} />
                <span className="min-w-0">
                  <span className="block text-[0.95rem] font-medium [overflow-wrap:anywhere] text-ink">
                    {kindName(provider)}
                  </span>
                  <span className="block text-[0.82rem] text-ink-muted">
                    {t("cfg-required-fields", { count: requiredCount(slot.kinds[kind] ?? {}) })}
                  </span>
                </span>
              </button>
            </li>
          );
        };
        return (
          <div className="grid gap-6">
            {groups.map((group) => (
              <section key={group.type ?? "all"} aria-label={group.type ? modelTypeLabel(group.type) : undefined}>
                {group.type ? (
                  <header className="mb-2.5">
                    <h3 className="text-[0.95rem] font-medium text-ink">{modelTypeLabel(group.type)}</h3>
                    <p className="text-[0.85rem] text-ink-muted">{modelTypeHint(group.type)}</p>
                  </header>
                ) : null}
                <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">{group.kinds.map(option)}</ul>
              </section>
            ))}
          </div>
        );
      }}
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
  tags = [],
  marks = [],
  problems,
  missing = false,
  onOpen,
}: {
  mark: ReactNode;
  title: string;
  line: string;
  detail?: string;
  tags?: string[];
  /** The channels a person is known on, as small marks. */
  marks?: string[];
  problems: number;
  missing?: boolean;
  onOpen: () => void;
}) {
  const t = useT();
  return (
    <li>
      <button type="button" onClick={onOpen} className="surface flex h-full w-full items-start gap-3.5 p-4 text-left">
        {mark}
        <span className="grid min-w-0 flex-1 gap-0.5">
          <span className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate font-medium text-ink">{title}</span>
            {marks.map((m) => (
              <KindMark key={m} kind={m} className="size-4 text-ink-muted" label={false} />
            ))}
          </span>
          <span className="truncate text-[0.9rem] text-ink-muted">{line}</span>
          {detail ? <span className="truncate text-[0.85rem] text-ink-faint">{detail}</span> : null}
          {tags.length ? (
            <span className="mt-1.5 flex flex-wrap gap-1.5">
              {tags.map((tag) => (
                <Tag key={tag}>{tag}</Tag>
              ))}
            </span>
          ) : null}
          {problems || missing ? (
            <Status tone="error" className="mt-1.5">
              {missing ? t("cfg-kind-missing-short") : t("cfg-problems", { count: problems })}
            </Status>
          ) : null}
        </span>
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
  return (
    <FormSheet
      open
      onOpenChange={(open) => !open && onClose()}
      title={title}
      description={
        mark ? (
          <span className="inline-flex items-center gap-1.5 text-[0.85rem]">
            <KindMark kind={mark} className="size-3.5" label={false} /> {kindName(mark)}
          </span>
        ) : undefined
      }
    >
      {() => (
        <div className="grid gap-6 pt-5">
          {children}
          <FormActions hint={t("cfg-sheet-note")}>
            {adding ? (
              onRemove ? (
                <Button variant="ghost" onClick={onRemove}>
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
                      <Button variant="ghost">
                        <Trash2 /> {t("cfg-remove")}
                      </Button>
                    }
                    title={removeTitle}
                    confirm={t("cfg-remove")}
                    onConfirm={async () => onRemove()}
                  >
                    {removeText}
                  </Confirm>
                ) : null}
              </>
            )}
            <Button onClick={onClose}>{t("cfg-done")}</Button>
          </FormActions>
        </div>
      )}
    </FormSheet>
  );
}
