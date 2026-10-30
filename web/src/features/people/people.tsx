import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, BookMarked, Gauge, House, MessageSquareText, Plug } from "lucide-react";
import type { ReactNode } from "react";
import { accountsQuery, connectionsQuery, journalFacetsQuery, type Person, type Presence, peopleQuery } from "@/api";
import { Ago } from "@/components/ago";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { TabNav } from "@/components/tab-nav";
import { ConnectionStatusMark } from "@/features/connections/status";
import { ActivityList } from "@/features/journal/activity-list";
import { SubjectStory } from "@/features/journal/subject-story";
import { MemoryList } from "@/features/memories/memories-view";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { startOfToday } from "@/lib/dates";
import { roleLabel } from "@/lib/labels";
import { useCan, useMe } from "@/lib/session";

export function PresenceMark({ presence }: { presence: Presence | null }) {
  const t = useT();
  if (!presence || presence.home === null) return <Status tone="idle">{t("people-presence-unknown")}</Status>;
  if (!presence.home) return <Status tone="idle">{t("people-presence-away")}</Status>;
  return (
    <Status tone="ok">
      {presence.room ? t("people-presence-home-room", { room: presence.room }) : t("people-presence-home")}
    </Status>
  );
}

export function PeopleList() {
  const t = useT();
  const people = useQuery(peopleQuery);
  if (people.isPending) return <Loading lines={3} />;
  if (people.isError) return <Failure error={people.error} retry={() => void people.refetch()} />;
  if (people.data.length === 0) return <Empty>{t("people-empty")}</Empty>;
  return (
    <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
      {people.data.map((p) => (
        <li key={p.id}>
          <Link
            to="/people/$personId"
            params={{ personId: p.id }}
            className="group grid grid-cols-[2.25rem_minmax(0,1fr)_auto] items-center gap-x-4 px-5 py-3.5 hover:bg-paper-sunken/60 sm:grid-cols-[2.25rem_minmax(0,1fr)_minmax(0,1fr)_12rem_1rem]"
          >
            <span
              aria-hidden="true"
              className="grid size-9 place-items-center rounded-sm bg-paper-sunken font-serif text-lg text-ink"
            >
              {p.name.slice(0, 1)}
            </span>
            <span>
              <span className="block text-ink">{p.name}</span>
              <span className="block font-mono text-[0.7rem] text-ink-muted">
                {p.account ? t("people-has-account") : t("people-no-account")}
              </span>
            </span>
            <span className="hidden flex-wrap gap-x-3 font-mono text-[0.7rem] text-ink-muted sm:flex">
              {p.channels.map((c) => (
                <span key={c} className="inline-flex items-center gap-1">
                  <KindMark kind={c} className="size-3" label={false} />
                  {c.split(":")[0]}
                </span>
              ))}
            </span>
            <PresenceMark presence={p.presence} />
            <ArrowRight className="hidden size-3.5 text-ink-faint group-hover:text-ink sm:block" aria-hidden="true" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function usePerson(id: string): { person: Person | undefined; pending: boolean; error: unknown } {
  const people = useQuery(peopleQuery);
  return { person: people.data?.find((p) => p.id === id), pending: people.isPending, error: people.error };
}

export function PersonFrame({ id, children }: { id: string; children: ReactNode }) {
  const t = useT();
  const { person, pending, error } = usePerson(id);
  const canConnections = useCan("connections:read");
  const trail: Crumb[] = [{ label: t("people-title"), link: { to: "/people" } }, { label: person?.name ?? id }];
  if (pending) return <Loading lines={3} />;
  if (!person) {
    return (
      <>
        <Crumbs trail={trail} />
        {error ? <Failure error={error} /> : <Empty>{t("people-not-found")}</Empty>}
      </>
    );
  }
  const base = `/people/${person.id}`;
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={person.name}
        meta={
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-ink-muted">
            <PresenceMark presence={person.presence} />
            {person.presence?.since ? (
              <span>
                {t("people-since")} <Ago iso={person.presence.since} />
              </span>
            ) : null}
          </p>
        }
      />
      <TabNav
        label={t("people-tabs", { name: person.name })}
        tabs={[
          { to: base, label: t("people-tab-overview"), icon: Gauge },
          { to: `${base}/conversations`, label: t("people-tab-conversations"), icon: MessageSquareText },
          { to: `${base}/memories`, label: t("people-tab-memories"), icon: BookMarked },
          ...(canConnections ? [{ to: `${base}/connections`, label: t("people-tab-connections"), icon: Plug }] : []),
          { to: `${base}/presence`, label: t("people-tab-presence"), icon: House },
        ]}
      />
      {children}
    </>
  );
}

export function PersonOverview({ person: p }: { person: Person }) {
  const t = useT();
  const me = useMe();
  const today = useQuery(journalFacetsQuery({ person: p.id, from: startOfToday() }));
  const accounts = useQuery({ ...accountsQuery, enabled: useCan("accounts:read") });
  const account = accounts.data?.find((a) => a.id === p.account);
  const kinds = new Map(today.data?.kinds.map((k) => [k.key, k.count]));
  return (
    <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_18rem] [&>*]:min-w-0">
      <div className="grid content-start gap-10">
        {today.data ? (
          <p className="max-w-2xl font-serif text-[1.2rem] leading-relaxed text-pretty [font-variation-settings:'opsz'_20]">
            {today.data.total
              ? t("people-today", {
                  name: p.name,
                  count: today.data.total,
                  spoken: kinds.get("delivery") ?? 0,
                  assistant: me.assistant,
                })
              : t("people-today-nothing", { name: p.name })}
          </p>
        ) : null}
        <Section title={t("people-recent")}>
          <ActivityList
            filters={{ person: p.id }}
            search={{ person: p.id }}
            limit={6}
            empty={t("people-recent-empty", { name: p.name })}
          />
        </Section>
      </div>
      <aside className="grid content-start gap-6 text-sm">
        <div>
          <p className="label-mono mb-1.5">{t("people-recognised-on")}</p>
          <ul className="grid gap-1">
            {p.channels.map((c) => (
              <li key={c} className="inline-flex items-center gap-2 font-mono text-[0.8rem]">
                <KindMark kind={c} className="size-3.5" />
                {c}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="label-mono mb-1.5">{t("people-reached-on")}</p>
          {p.reach ? (
            <p className="inline-flex items-center gap-2 font-mono text-[0.8rem]">
              <KindMark kind={p.reach} className="size-3.5" />
              {p.reach}
            </p>
          ) : (
            <p className="text-ink-muted">{t("people-reached-origin")}</p>
          )}
        </div>
        <div>
          <p className="label-mono mb-1.5">{t("people-admin")}</p>
          {account ? (
            <Link to="/accounts/$accountId" params={{ accountId: account.id }} className="text-ink hover:text-ember">
              {account.login} · {roleLabel(account.role)}
            </Link>
          ) : (
            <p className="text-ink-muted">{p.account ? t("people-has-account") : t("people-no-account")}</p>
          )}
        </div>
      </aside>
    </div>
  );
}

export function PersonConversations({ person: p }: { person: Person }) {
  const t = useT();
  return (
    <SubjectStory
      filters={{ person: p.id, kinds: ["conversation", "tool", "memory"] }}
      empty={t("people-conversations-empty", { name: p.name })}
    />
  );
}

export function PersonMemories({ person: p }: { person: Person }) {
  return <MemoryList query={{ about: p.id }} />;
}

export function PersonConnections({ person: p }: { person: Person }) {
  const t = useT();
  const connections = useQuery(connectionsQuery);
  if (connections.isPending) return <Loading lines={2} />;
  const own = (connections.data ?? []).filter((c) => c.owner === p.id);
  if (own.length === 0) {
    return (
      <Empty
        hint={t("people-connections-hint")}
        action={
          <Link to="/connections/catalogue" className="font-mono text-xs text-ember hover:underline">
            {t("people-open-catalogue")}
          </Link>
        }
      >
        {t("people-connections-empty", { name: p.name })}
      </Empty>
    );
  }
  return (
    <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
      {own.map((c) => (
        <li key={c.id}>
          <Link
            to="/connections/$connectionId"
            params={{ connectionId: c.id }}
            className="grid grid-cols-[1.5rem_1fr_auto] items-center gap-x-4 px-5 py-3 hover:bg-paper-sunken/60"
          >
            <KindMark kind={c.brand ?? c.kind} className="size-5" />
            <span>
              <span className="block text-ink">{c.account}</span>
              <span className="font-mono text-[0.7rem] text-ink-muted">{c.title}</span>
            </span>
            <ConnectionStatusMark status={c.status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function PersonPresence({ person: p }: { person: Person }) {
  const t = useT();
  return (
    <ActivityList
      filters={{ person: p.id, kinds: ["presence"] }}
      search={{ person: p.id, kinds: "presence" }}
      limit={20}
      empty={t("people-presence-empty")}
    />
  );
}
