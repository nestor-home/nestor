/**
 * "Connections": the accounts and services the agent uses for the household. Those it can no longer use come
 * first and say what to do; each account leads to its page.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Plus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { type Connection, connectionsQuery } from "@/api";
import { Ago } from "@/components/ago";
import { TILE_CARD, TileCard } from "@/components/card";
import { Chips } from "@/components/chips";
import { Crumbs } from "@/components/crumbs";
import { OwnerMark, ServiceTile } from "@/components/marks";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";
import { useT } from "@/i18n";
import { rendered } from "@/lib/messages";
import { personName } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { ConnectionStatusMark, needsSomeone } from "./status";
import { trail } from "./trail";

const HOUSEHOLD = "household";
const lane = (c: Connection) => c.owner?.id ?? HOUSEHOLD;

export function ConnectionsView() {
  const t = useT();
  const me = useMe();
  const canConnect = useCan("connections:write");
  const connections = useQuery(connectionsQuery);
  const [shown, setShown] = useState("all");

  const all = [...(connections.data ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const owners = [...new Map(all.map((c) => [lane(c), c.owner])).entries()];
  const lanes = [
    { id: "all", label: t("conn-lane-all") },
    { id: "attention", label: t("conn-lane-attention"), count: all.filter(needsSomeone).length },
    ...(owners.length > 1
      ? owners.map(([id, owner]) => ({
          id: `of:${id}`,
          label: owner ? owner.name : t("household-everyone-capital"),
          count: all.filter((c) => lane(c) === id).length,
        }))
      : []),
  ];
  const list = all.filter(
    (c) => shown === "all" || (shown === "attention" ? needsSomeone(c) : `of:${lane(c)}` === shown),
  );
  const broken = list.filter(needsSomeone);
  const working = list.filter((c) => !needsSomeone(c));

  return (
    <div className="grid gap-10">
      <div>
        <PageHeader
          crumbs={<Crumbs trail={trail()} />}
          title={t("conn-title")}
          actions={
            canConnect ? (
              <Link to="/connections/catalogue" className={buttonVariants()}>
                <Plus aria-hidden="true" /> {t("conn-connect-service")}
              </Link>
            ) : null
          }
        >
          {t("conn-intro", { assistant: me.assistant })}
        </PageHeader>
        {all.length ? <Chips label={t("conn-lanes")} items={lanes} value={shown} onChange={setShown} /> : null}
      </div>

      {connections.isPending ? (
        <Loading lines={3} />
      ) : connections.isError ? (
        <Failure error={connections.error} retry={() => void connections.refetch()} />
      ) : all.length === 0 ? (
        <Empty
          hint={t("conn-empty-hint")}
          action={
            <Link to="/connections/catalogue" className={buttonVariants({ size: "sm" })}>
              {t("conn-open-catalogue")}
            </Link>
          }
        >
          {t("conn-empty")}
        </Empty>
      ) : (
        <>
          {broken.length || shown === "attention" ? (
            <Section title={t("conn-attention-title")} count={broken.length}>
              {broken.length ? (
                <ul className="grid gap-3 lg:grid-cols-2">
                  {broken.map((c) => (
                    <BrokenCard key={c.id} connection={c} />
                  ))}
                </ul>
              ) : (
                <Empty>{t("conn-attention-empty", { assistant: me.assistant })}</Empty>
              )}
            </Section>
          ) : null}
          {working.length ? (
            <Section title={t("conn-working-title")} count={working.length}>
              <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {working.map((c) => (
                  <AccountCard key={c.id} connection={c} />
                ))}
              </ul>
            </Section>
          ) : null}
        </>
      )}
    </div>
  );
}

/** An account the agent lost: why, what to do, and the way to do it. */
function BrokenCard({ connection: c }: { connection: Connection }) {
  const t = useT();
  const me = useMe();
  const canConnect = useCan("connections:write");
  return (
    <li className="surface flex gap-4 p-4">
      <ServiceTile kind={c.brand ?? c.kind} />
      <div className="min-w-0 flex-1">
        <ConnectionStatusMark status={c.status} />
        <Link
          to="/connections/$connectionId"
          params={{ connectionId: c.id }}
          className="mt-0.5 block truncate text-lead font-medium text-ink hover:underline"
        >
          {c.account}
        </Link>
        <p className="text-body text-ink-muted">
          {c.title} · {personName(c.owner)}
        </p>
        <p className="mt-2 text-body text-ink">
          {t(c.status === "needs_reauth" ? "conn-fix-reauth" : "conn-fix-error", { assistant: me.assistant })}
        </p>
        {c.status_reason ? (
          <p className="mt-1 font-mono text-meta [overflow-wrap:anywhere] text-ink-muted">
            {rendered(c.status_reason)}
          </p>
        ) : null}
        {canConnect ? (
          <Link
            to="/connections/catalogue"
            search={{ connect: c.kind, replaces: c.id }}
            className={buttonVariants({ size: "sm", className: "mt-3" })}
          >
            <RefreshCw aria-hidden="true" /> {t("conn-reconnect-ellipsis")}
          </Link>
        ) : null}
      </div>
      <OwnerMark owner={c.owner} />
    </li>
  );
}

function AccountCard({ connection: c }: { connection: Connection }) {
  const t = useT();
  return (
    <li>
      <Link to="/connections/$connectionId" params={{ connectionId: c.id }} className={TILE_CARD}>
        <TileCard
          marks={<ServiceTile kind={c.brand ?? c.kind} />}
          aside={<OwnerMark owner={c.owner} />}
          title={c.account}
          line={`${c.title} · ${personName(c.owner)}`}
          foot={
            <>
              <ConnectionStatusMark status={c.status} />
              {c.last_used_at ? (
                <span>
                  {t("conn-last-used")} <Ago iso={c.last_used_at} />
                </span>
              ) : (
                <span>{t("conn-never-used-short")}</span>
              )}
            </>
          }
        />
      </Link>
    </li>
  );
}
