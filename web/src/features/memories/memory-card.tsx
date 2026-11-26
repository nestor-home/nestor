import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight, BookMarked, FolderInput, Pencil, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import { api, type Memory, memoriesQuery, type Place, peopleQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Choice, type ChoiceOption } from "@/components/choice";
import { Confirm } from "@/components/confirm";
import { Field } from "@/components/field";
import { FormActions } from "@/components/form-actions";
import { Avatar } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { FormDialog, SheetPanel } from "@/components/overlay-form";
import { Fact, Facts } from "@/components/page";
import { FormError } from "@/components/states";
import { Tag } from "@/components/status";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import { KindMark, kindName } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { useCan } from "@/lib/session";
import { named, PlaceIcon, placeName, readable } from "./places";

/** What a memory is tied to (`task:3f2a`), read: it is retired when that ends. */
export function tieOf(tied: string | null): { kind: string; id: string } | null {
  if (!tied) return null;
  const [kind = "", ...rest] = tied.split(":");
  return { kind, id: rest.join(":") };
}

/** One thing the agent knows, in its own words; `place` says where it is filed when the list does not. */
export function MemoryCard({ memory, place, onOpen }: { memory: Memory; place: boolean; onOpen: () => void }) {
  const t = useT();
  const where = placeName(t, memory.place);
  return (
    <li>
      <button type="button" className="surface flex h-full w-full flex-col gap-3 p-4 text-left" onClick={onOpen}>
        <span className="min-w-0 flex-1 title-sub text-ink [font-variation-settings:'opsz'_18]">{memory.text}</span>
        <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-ink-muted">
          {place ? (
            <span className="inline-flex min-w-0 items-center gap-1.5 text-ink">
              <PlaceIcon place={memory.place} name={where} />
              {where}
            </span>
          ) : null}
          {memory.told_by ? <span>{t("mem-told-by", { name: memory.told_by.name })}</span> : null}
          <Ago iso={memory.updated_at} />
        </span>
      </button>
    </li>
  );
}

/** A memory, opened: whom it is about, who said it and where, then correcting or forgetting it. */
export function MemoryPanel({ memory, editable, onDone }: { memory: Memory; editable: boolean; onDone: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const tie = tieOf(memory.tied_to);
  const forget = useMutation({
    mutationFn: () => api.forgetMemory(memory.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["memories"] });
      notify(t("mem-forgotten"));
      onDone();
    },
  });
  return (
    <SheetPanel
      icon={BookMarked}
      tone="sage"
      kind={t("mem-kind")}
      title={memory.text}
      actions={
        memory.learnt_event || editable ? (
          <>
            {memory.learnt_event ? (
              <Link
                to="/journal"
                search={{ event: memory.learnt_event, ...(memory.session ? { session: memory.session } : {}) }}
                className={buttonVariants({ variant: "outline" })}
              >
                {t("mem-learnt-where")} <ArrowUpRight />
              </Link>
            ) : null}
            {editable ? (
              <>
                <FormDialog
                  trigger={
                    <Button variant="outline">
                      <Pencil /> {t("mem-correct")}
                    </Button>
                  }
                  title={t("mem-correct-title")}
                  description={t("mem-correct-description")}
                >
                  {(close) => <CorrectForm memory={memory} onDone={close} />}
                </FormDialog>
                <FormDialog
                  trigger={
                    <Button variant="outline">
                      <FolderInput /> {t("mem-move")}
                    </Button>
                  }
                  title={t("mem-move-title")}
                >
                  {(close) => <MoveForm memory={memory} onDone={close} />}
                </FormDialog>
                <Confirm
                  trigger={
                    <Button variant="destructive">
                      <Trash2 /> {t("mem-forget")}
                    </Button>
                  }
                  title={t("mem-forget-title")}
                  confirm={t("mem-forget-confirm")}
                  onConfirm={() => forget.mutateAsync()}
                >
                  {t("mem-forget-text", { text: memory.text })}
                </Confirm>
              </>
            ) : null}
          </>
        ) : undefined
      }
    >
      <Facts narrow className="text-body">
        <Fact term={t("mem-place")}>
          <PlaceLine place={memory.place} />
        </Fact>
        {memory.told_by ? <Fact term={t("mem-told-by-label")}>{memory.told_by.name}</Fact> : null}
        {memory.learnt_in ? (
          <Fact term={t("mem-learnt-in")} className="flex items-center gap-1.5">
            <KindMark kind={memory.learnt_in} className="size-3.5" label={false} />
            {kindName(memory.learnt_in)}
          </Fact>
        ) : null}
        {tie ? (
          <Fact term={t("mem-tied")}>
            <TieLink kind={tie.kind} id={tie.id} />
          </Fact>
        ) : null}
        <Fact term={t("mem-kept-since")}>{moment(memory.created_at)}</Fact>
        {memory.updated_at === memory.created_at ? null : (
          <Fact term={t("mem-changed")}>
            <Ago iso={memory.updated_at} />
          </Fact>
        )}
      </Facts>
    </SheetPanel>
  );
}

function CorrectForm({ memory, onDone }: { memory: Memory; onDone: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const [text, setText] = useState(memory.text);
  const correct = useMutation({
    mutationFn: () => api.correctMemory(memory.id, text.trim()),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["memories"] });
      notify(t("mem-corrected"));
      onDone();
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    correct.mutate();
  }
  const id = `memory-${memory.id}`;
  return (
    <form onSubmit={submit} className="grid gap-3">
      <Label htmlFor={id}>{t("mem-text")}</Label>
      <Textarea
        id={id}
        rows={3}
        required
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
        }}
      />
      <FormError error={correct.error} />
      <FormActions hint={t("mem-save-hint")}>
        <Button type="submit" disabled={correct.isPending || !text.trim() || text.trim() === memory.text}>
          {correct.isPending ? t("action-saving") : t("action-save")}
        </Button>
      </FormActions>
    </form>
  );
}

/** Where a memory is filed, in its sheet: a person leads to their page, a project or a topic says which it is. */
function PlaceLine({ place }: { place: Place }) {
  const t = useT();
  const name = placeName(t, place);
  if (place.person) {
    return (
      <Link
        to="/people/$personId"
        params={{ personId: place.person.id }}
        className="inline-flex items-center gap-2 text-ink hover:text-ember"
      >
        <Avatar name={name} size="sm" />
        {name}
      </Link>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <PlaceIcon place={place} name={name} />
      {name}
      {named(place.shelf) ? <Tag>{t("mem-shelf-kind", { shelf: place.shelf })}</Tag> : null}
    </span>
  );
}

/** Until what a memory holds: its task's page, or its name. */
function TieLink({ kind, id }: { kind: string; id: string }) {
  const t = useT();
  const label = t("mem-tied-to", { kind });
  const className = "inline-flex items-center gap-1 text-ink hover:text-ember";
  if (kind === "task") {
    return (
      <Link to="/tasks/$taskId" params={{ taskId: id }} className={className}>
        {label} <ArrowUpRight className="size-3.5" aria-hidden="true" />
      </Link>
    );
  }
  return <span>{label}</span>;
}

const NEW = { projects: "new:projects", topics: "new:topics" } as const;

/** Filing a memory elsewhere: a person, the house, the household, a project or topic already there, or a new one. */
function MoveForm({ memory, onDone }: { memory: Memory; onDone: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const people = useQuery({ ...peopleQuery, enabled: useCan("people:read") });
  const projects = useQuery(memoriesQuery({ place: "projects", limit: 200 }));
  const topics = useQuery(memoriesQuery({ place: "topics", limit: 200 }));
  const [choice, setChoice] = useState(memory.place.path);
  const [name, setName] = useState("");
  const fresh = choice === NEW.projects || choice === NEW.topics;
  const target = fresh ? `${choice.slice("new:".length)}/${name.trim()}` : choice;
  const move = useMutation({
    mutationFn: () => api.moveMemory(memory.id, target),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["memories"] });
      notify(t("mem-moved"));
      onDone();
    },
  });
  const persons: ChoiceOption<string>[] = people.data
    ? people.data.map((p) => ({ value: `people/${p.id}`, label: p.name }))
    : memory.place.shelf === "people"
      ? [{ value: memory.place.path, label: placeName(t, memory.place) }]
      : [];
  const existing = new Map<string, Place>();
  for (const m of [memory, ...(projects.data ?? []), ...(topics.data ?? [])]) {
    if (named(m.place.shelf)) existing.set(m.place.path, m.place);
  }
  const options: ChoiceOption<string>[] = [
    ...persons,
    { value: "home", label: t("mem-shelf-home") },
    { value: "household", label: t("mem-shelf-household") },
    ...[...existing.values()]
      .sort((a, b) => a.shelf.localeCompare(b.shelf) || (a.name ?? "").localeCompare(b.name ?? ""))
      .map((p) => ({
        value: p.path,
        label: t("mem-place-option", { shelf: p.shelf, name: readable(p.name ?? "") }),
      })),
    { value: NEW.projects, label: t("mem-move-new-project") },
    { value: NEW.topics, label: t("mem-move-new-topic") },
  ];
  function submit(event: FormEvent) {
    event.preventDefault();
    move.mutate();
  }
  return (
    <form onSubmit={submit} className="grid gap-4">
      <Field label={t("mem-move-where")} htmlFor="memory-place">
        <Choice id="memory-place" value={choice} options={options} onChange={setChoice} />
      </Field>
      {fresh ? (
        <Field label={t("mem-move-name")} htmlFor="memory-place-name">
          <Input
            id="memory-place-name"
            required
            autoFocus
            placeholder={t("mem-move-name-placeholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
      ) : null}
      <FormError error={move.error} />
      <FormActions>
        <Button type="submit" disabled={move.isPending || target === memory.place.path || (fresh && !name.trim())}>
          {t("mem-move-submit")}
        </Button>
      </FormActions>
    </form>
  );
}
