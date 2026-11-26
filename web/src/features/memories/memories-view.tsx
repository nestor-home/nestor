/**
 * What the agent knows about the household, by where it is filed: each person, the house, the household's shared
 * life, then the projects and the topics the agent named. A memory opens in a sheet (where it comes from,
 * correcting, moving or forgetting it), searching is a dialog opened from the page's heading, and what the nightly
 * upkeep or an ending tidied away closes the page.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Search, X } from "lucide-react";
import { type FormEvent, useState } from "react";
import { type Memory, type MemoryQuery, memoriesQuery, peopleQuery, type Retired, retiredQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Chips } from "@/components/chips";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { FormActions } from "@/components/form-actions";
import { Avatar, IconTile } from "@/components/marks";
import { FormDialog, SideSheet } from "@/components/overlay-form";
import { PageHeader, RowList, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Tag } from "@/components/status";
import { Button } from "@/components/ui/button";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Label } from "@/components/ui/label";
import { useT } from "@/i18n";
import { RETIREMENT_ICON, SHELF_ICON } from "@/lib/icons";
import { useCan, useMe } from "@/lib/session";
import { MemoryCard, MemoryPanel, tieOf } from "./memory-card";
import { byPlace, named, PlaceIcon, placeName } from "./places";

/** The memories a query brings, as cards that open in place; `grouped` files them under their place. */
export function MemoryList({ query, grouped = false }: { query: MemoryQuery; grouped?: boolean }) {
  const t = useT();
  const memories = useQuery(memoriesQuery(query));
  const people = useQuery({ ...peopleQuery, enabled: useCan("people:read") && grouped });
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
        <MemoryCard key={m.id} memory={m} place={!grouped} onOpen={() => setOpen(m.id)} />
      ))}
    </ul>
  );
  return (
    <>
      {grouped ? (
        <div className="grid gap-10">
          {byPlace(
            memories.data,
            (people.data ?? []).map((p) => p.id),
          ).map(({ place, list }) => {
            const name = placeName(t, place);
            return (
              <Section
                key={place.path}
                id={`place-${place.path.replace(/[^a-z0-9]+/gi, "-")}`}
                title={name}
                count={list.length}
                mark={
                  place.shelf === "people" ? undefined : (
                    <IconTile icon={SHELF_ICON[place.shelf]} size="sm" tone="sage" />
                  )
                }
                aside={
                  place.person ? (
                    <Link
                      to="/people/$personId"
                      params={{ personId: place.person.id }}
                      className="inline-flex shrink-0 items-center gap-2 text-body text-ink-muted hover:text-ink"
                      aria-label={t("mem-open-person", { name })}
                    >
                      <Avatar name={name} />
                      <ArrowRight className="size-3.5" aria-hidden="true" />
                    </Link>
                  ) : named(place.shelf) ? (
                    <Tag className="shrink-0">{t("mem-shelf-kind", { shelf: place.shelf })}</Tag>
                  ) : undefined
                }
              >
                {cards(list)}
              </Section>
            );
          })}
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

/** What the nightly upkeep merged or set aside, and what went when its task ended: each opens its journal entry. */
function Tidied() {
  const t = useT();
  const retired = useQuery(retiredQuery);
  const memories = useQuery(memoriesQuery({}));
  const body = retired.isPending ? (
    <Loading lines={2} />
  ) : retired.isError ? (
    <Failure error={retired.error} retry={() => void retired.refetch()} />
  ) : retired.data.length === 0 ? (
    <Empty hint={t("mem-tidied-empty-hint")}>{t("mem-tidied-empty")}</Empty>
  ) : (
    <RowList aria-label={t("mem-tidied")}>
      {retired.data.map((r) => (
        <TidiedRow key={`${r.event}`} retired={r} into={memories.data?.find((m) => m.id === r.into)} />
      ))}
    </RowList>
  );
  return (
    <Section title={t("mem-tidied")} count={retired.data?.length} id="memories-tidied">
      {body}
    </Section>
  );
}

function TidiedRow({ retired: r, into }: { retired: Retired; into: Memory | undefined }) {
  const t = useT();
  const where = placeName(t, r.place);
  const what =
    r.reason === "merged" && into
      ? t("mem-retired-into", { text: into.text })
      : t("mem-retired", { reason: r.reason, tie: tieOf(r.tied_to)?.kind ?? "" });
  return (
    <li>
      <Link
        to="/journal"
        search={{ event: r.event }}
        className="grid grid-cols-[auto_1fr] gap-x-3.5 px-4 py-3 hover:bg-paper-sunken/60"
      >
        <IconTile icon={RETIREMENT_ICON[r.reason]} size="sm" />
        <span className="grid min-w-0 gap-1 [overflow-wrap:break-word]">
          <span className="text-body text-ink">{what}</span>
          <span className="text-meta text-ink-muted line-through decoration-rule-strong">{r.text}</span>
          {r.why ? (
            <span className="text-meta text-ink-muted">
              <span className="text-ember">{t("jr-why-label")} </span>
              {r.why}
            </span>
          ) : null}
          <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-ink-muted">
            <span className="inline-flex min-w-0 items-center gap-1.5">
              <PlaceIcon place={r.place} name={where} />
              {where}
            </span>
            <Ago iso={r.at} />
          </span>
        </span>
      </Link>
    </li>
  );
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
  const filtered = Boolean(query.q || query.about);
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
      {filtered ? null : <Tidied />}
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
