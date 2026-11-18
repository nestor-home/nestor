/**
 * A person of the household: who they are and where they are now, how the agent reaches and recognises
 * them, then what concerns them (conversations, memories, connected accounts, presence).
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, BookMarked, Gauge, House, MessageSquareText, Plug, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { connectionsQuery, isMissing, journalFacetsQuery, type Person, type Presence, personQuery } from "@/api";
import { Ago } from "@/components/ago";
import { CardHead, OpenArrow } from "@/components/card";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { AddCard, Avatar, IconTile, ServiceTile } from "@/components/marks";
import { Lead, PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status, Tag } from "@/components/status";
import { TabNav } from "@/components/tab-nav";
import { buttonVariants } from "@/components/ui/button";
import { ConnectionCard } from "@/features/connections/parts";
import { ActivityList } from "@/features/journal/activity-list";
import { SubjectStory } from "@/features/journal/subject-story";
import { MemoryList } from "@/features/memories/memories-view";
import { useT } from "@/i18n";
import { KindMark, kindName } from "@/lib/brands";
import { startOfToday } from "@/lib/dates";
import { roleLabel } from "@/lib/labels";
import { useCan, useMe } from "@/lib/session";
import { PersonVoice } from "./voice";

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

export function usePerson(id: string): { person: Person | undefined; pending: boolean; error: unknown } {
  const found = useQuery(personQuery(id));
  return { person: found.data, pending: found.isPending, error: isMissing(found.error) ? null : found.error };
}

/** The person, then the pages of what concerns them. */
export function PersonFrame({ id, children }: { id: string; children: ReactNode }) {
  const t = useT();
  const { person, pending, error } = usePerson(id);
  const canConnections = useCan("connections:read");
  const trail: Crumb[] = [{ label: t("space-house"), link: { to: "/house" } }, { label: person?.name ?? id }];
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
        mark={<Avatar name={person.name} away={person.presence?.home === false} size="2xl" />}
        title={person.name}
        meta={
          <>
            <PresenceMark presence={person.presence} />
            {person.presence?.since ? (
              <span>
                {t("people-since")} <Ago iso={person.presence.since} />
              </span>
            ) : null}
            {person.reach ? (
              <span className="inline-flex items-center gap-1.5">
                <KindMark kind={person.reach} className="size-3.5" label={false} />
                {t("people-reached-on", { channel: kindName(person.reach) })}
              </span>
            ) : null}
          </>
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

/** What comes after the colon of a channel account (`telegram:@lea` → `@lea`), when there is one. */
const handleOf = (account: string) => account.split(":").slice(1).join(":");

/** One way to the person: the channel's mark, its name, the handle they are known by there. */
function Channel({ account, first }: { account: string; first: boolean }) {
  const t = useT();
  const handle = handleOf(account);
  return (
    <li className="surface p-4">
      <CardHead
        mark={<ServiceTile kind={account} />}
        title={kindName(account)}
        line={handle ? <span className="font-mono text-meta">{handle}</span> : null}
        aside={first ? <Tag tone="accent">{t("people-reach-first")}</Tag> : null}
      />
    </li>
  );
}

/** Whether the person can open this interface, and with which account. */
function AdminAccess({ person: p }: { person: Person }) {
  const t = useT();
  const account = useCan("accounts:read") ? p.account : null;
  return (
    <CardHead
      mark={<IconTile icon={UserRound} tone={p.account ? "sage" : "ink"} />}
      title={t("people-admin")}
      line={
        account
          ? `${account.login} · ${roleLabel(account.role)}`
          : p.account
            ? t("people-has-account")
            : t("people-no-account")
      }
      aside={account ? <OpenArrow /> : null}
    />
  );
}

export function PersonOverview({ person: p }: { person: Person }) {
  const t = useT();
  const me = useMe();
  const today = useQuery(journalFacetsQuery({ person: p.id, from: startOfToday() }));
  const account = useCan("accounts:read") ? p.account : null;
  const kinds = new Map(today.data?.kinds.map((k) => [k.key, k.count]));
  // the channel written to first may be one the person is not recognised on (the voice of the room they are in)
  const channels =
    p.reach && !p.channel_accounts.includes(p.reach) ? [p.reach, ...p.channel_accounts] : p.channel_accounts;
  return (
    <div className="grid gap-10">
      {today.data ? (
        <Lead>
          {today.data.total
            ? t("people-today", {
                name: p.name,
                count: today.data.total,
                spoken: kinds.get("delivery") ?? 0,
                assistant: me.assistant,
              })
            : t("people-today-nothing", { name: p.name })}
        </Lead>
      ) : null}

      <Section title={t("people-reach-title", { assistant: me.assistant })}>
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {channels.map((c) => (
            <Channel key={c} account={c} first={c === p.reach} />
          ))}
          <li>
            {account ? (
              <Link
                to="/accounts/$accountId"
                params={{ accountId: account.id }}
                className="group surface block h-full p-4"
                aria-label={t("people-open-account", { login: account.login })}
              >
                <AdminAccess person={p} />
              </Link>
            ) : (
              <div className="surface h-full p-4">
                <AdminAccess person={p} />
              </div>
            )}
          </li>
        </ul>
        {p.reach ? null : (
          <p className="mt-3 text-body text-ink-muted">{t("people-reached-origin", { assistant: me.assistant })}</p>
        )}
      </Section>

      <PersonVoice person={p} />

      <Section title={t("people-recent")}>
        <ActivityList
          filters={{ person: p.id }}
          search={{ person: p.id }}
          limit={6}
          empty={t("people-recent-empty", { name: p.name })}
        />
      </Section>
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
  const canConnect = useCan("connections:write");
  if (connections.isPending) return <Loading lines={2} />;
  const own = (connections.data ?? []).filter((c) => c.owner?.id === p.id);
  if (own.length === 0) {
    return (
      <Empty
        hint={t("people-connections-hint")}
        action={
          <Link
            to="/connections/catalogue"
            search={{ owner: p.id }}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            {t("people-open-catalogue")} <ArrowRight />
          </Link>
        }
      >
        {t("people-connections-empty", { name: p.name })}
      </Empty>
    );
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {own.map((c) => (
        <ConnectionCard key={c.id} connection={c} />
      ))}
      {canConnect ? (
        <li>
          <AddCard link={{ to: "/connections/catalogue", search: { owner: p.id } }}>{t("people-connect")}</AddCard>
        </li>
      ) : null}
    </ul>
  );
}

export function PersonPresence({ person: p }: { person: Person }) {
  const t = useT();
  return (
    <ActivityList
      filters={{ person: p.id, kinds: ["presence"] }}
      search={{ person: p.id, kinds: ["presence"] }}
      limit={20}
      empty={t("people-presence-empty")}
    />
  );
}
