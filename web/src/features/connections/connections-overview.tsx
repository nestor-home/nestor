import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { type Connection, connectionsQuery, connectorsQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Panel } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Tag } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { authLabel } from "@/lib/labels";
import { usePeopleNames } from "@/lib/people";
import { useCan } from "@/lib/session";
import { ConnectionStatusMark } from "./status";

/** The accounts plugged in, the broken ones first: they are the ones that need someone. */
export function ConnectedAccounts() {
  const connections = useQuery(connectionsQuery);
  const name = usePeopleNames();
  const t = useT();
  if (connections.isPending) return <Loading lines={3} />;
  if (connections.isError) return <Failure error={connections.error} retry={() => void connections.refetch()} />;
  const rank = (c: Connection) => (c.status === "connected" ? 1 : 0);
  const list = [...connections.data].sort((a, b) => rank(a) - rank(b) || a.created_at.localeCompare(b.created_at));
  if (list.length === 0) {
    return (
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
    );
  }
  return (
    <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
      {list.map((c) => (
        <li key={c.id}>
          <Link
            to="/connections/$connectionId"
            params={{ connectionId: c.id }}
            className="group grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-5 py-3.5 hover:bg-paper-sunken/60 sm:grid-cols-[1.5rem_minmax(0,2fr)_minmax(0,1.2fr)_8.5rem_1rem]"
          >
            <KindMark kind={c.brand ?? c.kind} className="size-5 text-ink" />
            <span className="min-w-0">
              <span className="block truncate text-ink">{c.account}</span>
              <span className="block text-[0.85rem] text-ink-muted">
                {c.title} · {name(c.owner)}
              </span>
            </span>
            <span className="hidden text-[0.85rem] text-ink-muted sm:block">
              {c.status === "connected" ? (
                <>
                  {t("conn-calls-today", { count: c.calls_today })}
                  {c.last_used_at ? (
                    <>
                      {" "}
                      · <Ago iso={c.last_used_at} />
                    </>
                  ) : null}
                </>
              ) : (
                <span className="text-amber">{c.status_reason}</span>
              )}
            </span>
            <ConnectionStatusMark status={c.status} />
            <ArrowRight className="hidden size-3.5 text-ink-faint group-hover:text-ink sm:block" aria-hidden="true" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function Catalogue({ onConnect }: { onConnect: (kind: string) => void }) {
  const connectors = useQuery(connectorsQuery);
  const connections = useQuery(connectionsQuery);
  const canConnect = useCan("connections:write");
  const t = useT();
  if (connectors.isPending) return <Loading lines={2} />;
  if (connectors.isError) return <Failure error={connectors.error} retry={() => void connectors.refetch()} />;
  if (connectors.data.length === 0) return <Empty>{t("conn-no-connector")}</Empty>;
  return (
    <ul className="grid gap-4 sm:grid-cols-2">
      {connectors.data.map((c) => {
        const plugged = (connections.data ?? []).filter((x) => x.kind === c.kind).length;
        return (
          <Panel as="li" key={c.kind} className="group flex flex-col">
            <div className="flex items-start gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-md border border-rule bg-paper">
                <KindMark kind={c.brand ?? c.kind} className="size-5 text-ink" />
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="text-lg leading-tight font-normal">{c.title}</h2>
                <p className="mt-0.5 text-[0.85rem] text-ink-muted">
                  {authLabel(c.auth)}
                  {c.inbound.length ? ` · ${t("conn-feeds-watches")}` : ""}
                  {plugged ? ` · ${t("conn-accounts-count", { count: plugged })}` : ""}
                </p>
              </div>
              {c.auth === "oauth2" && !c.client ? <Tag tone="attention">{t("conn-client-to-create")}</Tag> : null}
            </div>
            <p className="mt-3 flex-1 text-sm text-ink-muted">{c.description}</p>
            {canConnect ? (
              <button
                type="button"
                onClick={() => onConnect(c.kind)}
                className={buttonVariants({ variant: "outline", size: "sm", className: "mt-4 self-start" })}
              >
                {t("conn-connect-ellipsis")}
              </button>
            ) : null}
          </Panel>
        );
      })}
    </ul>
  );
}
