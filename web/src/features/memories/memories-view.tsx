/**
 * What the agent knows about the household, by person: a memory opens in a sheet (where it comes from,
 * correcting it, forgetting it), and searching is a dialog opened from the page's heading.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Search, X } from "lucide-react";
import { type FormEvent, useState } from "react";
import { type Memory, type MemoryQuery, memoriesQuery, peopleQuery } from "@/api";
import { Chips } from "@/components/chips";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { FormActions } from "@/components/form-actions";
import { Avatar } from "@/components/marks";
import { FormDialog, SideSheet } from "@/components/overlay-form";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Label } from "@/components/ui/label";
import { useT } from "@/i18n";
import { useCan, useMe } from "@/lib/session";
import { MemoryCard, MemoryPanel } from "./memory-card";

/** The memories a query brings, as cards that open in place; `grouped` sorts them under whom they are about. */
export function MemoryList({ query, grouped = false }: { query: MemoryQuery; grouped?: boolean }) {
  const t = useT();
  const memories = useQuery(memoriesQuery(query));
  const editable = useCan("memories:write");
  const [open, setOpen] = useState<string | null>(null);
  if (memories.isPending) return <Loading lines={4} />;
  if (memories.isError) return <Failure error={memories.error} retry={() => void memories.refetch()} />;
  if (memories.data.length === 0) {
    return (
      <Empty hint={query.q ? undefined : t("mem-empty-hint")}>{query.q ? t("mem-empty-search") : t("mem-empty")}</Empty>
    );
  }
  const opened = memories.data.find((m) => m.id === open);
  const cards = (list: readonly Memory[]) => (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {list.map((m) => (
        <MemoryCard key={m.id} memory={m} about={!grouped} onOpen={() => setOpen(m.id)} />
      ))}
    </ul>
  );
  return (
    <>
      {grouped ? (
        <div className="grid gap-10">
          {groupsOf(memories.data).map(({ about, list }) => (
            <Section
              key={about?.id ?? ""}
              title={about?.name ?? t("household-everyone-capital")}
              count={list.length}
              aside={
                about ? (
                  <Link
                    to="/people/$personId"
                    params={{ personId: about.id }}
                    className="inline-flex shrink-0 items-center gap-2 text-body text-ink-muted hover:text-ink"
                    aria-label={t("mem-open-person", { name: about.name })}
                  >
                    <Avatar name={about.name} />
                    <ArrowRight className="size-3.5" aria-hidden="true" />
                  </Link>
                ) : undefined
              }
            >
              {cards(list)}
            </Section>
          ))}
        </div>
      ) : (
        cards(memories.data)
      )}
      <SideSheet open={Boolean(opened)} onOpenChange={(next) => !next && setOpen(null)}>
        {opened ? <MemoryPanel memory={opened} editable={editable} onDone={() => setOpen(null)} /> : null}
      </SideSheet>
    </>
  );
}

/** Memories under whom they are about, in the order they came: the whole household's first. */
function groupsOf(memories: readonly Memory[]): { about: Memory["about"]; list: Memory[] }[] {
  const groups = new Map<string, { about: Memory["about"]; list: Memory[] }>();
  for (const m of memories) {
    const key = m.about?.id ?? "";
    const group = groups.get(key) ?? { about: m.about, list: [] };
    group.list.push(m);
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => Number(Boolean(a.about)) - Number(Boolean(b.about)));
}

export function MemoriesView({ query, onQuery }: { query: MemoryQuery; onQuery: (next: MemoryQuery) => void }) {
  const t = useT();
  const me = useMe();
  const people = useQuery({ ...peopleQuery, enabled: useCan("people:read") });
  const trail: Crumb[] = [{ label: t("space-house"), link: { to: "/house" } }, { label: t("mem-title") }];
  const lanes = [
    { id: "", label: t("mem-about-everyone") },
    ...(people.data ?? []).map((p) => ({ id: p.id, label: p.name })),
  ];
  return (
    <div className="grid gap-10">
      <div>
        <PageHeader
          crumbs={<Crumbs trail={trail} />}
          title={t("mem-title")}
          actions={
            <FormDialog
              trigger={
                <Button variant="outline">
                  <Search /> {t("mem-search-open")}
                </Button>
              }
              title={t("mem-search-title")}
            >
              {(close) => (
                <SearchForm
                  initial={query.q ?? ""}
                  onSearch={(q) => {
                    onQuery({ ...query, q });
                    close();
                  }}
                />
              )}
            </FormDialog>
          }
        >
          {t("mem-lede", { assistant: me.assistant })}
        </PageHeader>
        <Chips
          label={t("mem-about")}
          items={lanes}
          value={query.about ?? ""}
          onChange={(about) => onQuery({ ...query, about: about || undefined })}
        />
        {query.q ? (
          <p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-body text-ink">
            {t("mem-search-for", { q: query.q })}
            <Button variant="ghost" size="sm" onClick={() => onQuery({ ...query, q: undefined })}>
              <X /> {t("mem-search-clear")}
            </Button>
          </p>
        ) : null}
      </div>
      <MemoryList query={query} grouped={!query.about} />
    </div>
  );
}

function SearchForm({ initial, onSearch }: { initial: string; onSearch: (q: string | undefined) => void }) {
  const t = useT();
  const [q, setQ] = useState(initial);
  function submit(event: FormEvent) {
    event.preventDefault();
    onSearch(q.trim() || undefined);
  }
  return (
    <form onSubmit={submit} className="grid gap-3">
      <Label htmlFor="memory-search">{t("mem-search")}</Label>
      <InputGroup>
        <InputGroupAddon>
          <Search aria-hidden="true" />
        </InputGroupAddon>
        <InputGroupInput
          id="memory-search"
          type="search"
          autoFocus
          placeholder={t("mem-search-placeholder")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </InputGroup>
      <FormActions>
        <Button type="submit">{t("mem-search-submit")}</Button>
      </FormActions>
    </form>
  );
}
