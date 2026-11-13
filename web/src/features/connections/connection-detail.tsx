import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Activity, Gauge, Settings2, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { api, type ConnectionDetail, connectionQuery, keys } from "@/api";
import { Confirm } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { useNotify } from "@/components/notices";
import { Lead, PageHeader, Panel, Section } from "@/components/page";
import { Failure, Loading } from "@/components/states";
import { TabNav } from "@/components/tab-nav";
import { Button, buttonVariants } from "@/components/ui/button";
import { ActivityList } from "@/features/journal/activity-list";
import { useT } from "@/i18n";
import { KindMark, kindName } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { rendered } from "@/lib/messages";
import { personName } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { ago } from "@/lib/time";
import { ConnectionStatusMark } from "./status";

export function useConnection(id: string) {
  return useQuery(connectionQuery(id));
}

/** The frame of a connection's pages: where it sits, what it is, its tabs. */
export function ConnectionFrame({ id, children }: { id: string; children: ReactNode }) {
  const connection = useConnection(id);
  const t = useT();
  const trail: Crumb[] = [
    { label: t("conn-title"), link: { to: "/connections" } },
    { label: connection.data?.account ?? id },
  ];
  if (connection.isPending) return <Loading lines={4} />;
  if (connection.isError) {
    return (
      <>
        <Crumbs trail={trail} />
        <Failure error={connection.error} retry={() => void connection.refetch()} />
      </>
    );
  }
  const c = connection.data;
  const enabled = c.tools.filter((tool) => tool.enabled).length;
  const base = `/connections/${c.id}`;
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={
          <span className="inline-flex items-center gap-3">
            <KindMark kind={c.brand ?? c.kind} className="size-7 text-ink" />
            {c.account}
          </span>
        }
        meta={
          <>
            <ConnectionStatusMark status={c.status} />
            <span>{c.title}</span>
            <span>{t("conn-owner", { name: personName(c.owner) })}</span>
            <span>{t("conn-connected-at", { when: moment(c.created_at) })}</span>
          </>
        }
      />
      <TabNav
        label={t("conn-sections")}
        tabs={[
          { to: base, label: t("conn-tab-overview"), icon: Gauge },
          { to: `${base}/tools`, label: t("conn-tools"), icon: Wrench, count: enabled },
          { to: `${base}/activity`, label: t("conn-tab-activity"), icon: Activity },
          { to: `${base}/settings`, label: t("conn-tab-settings"), icon: Settings2 },
        ]}
      />
      {children}
    </>
  );
}

export function ConnectionOverview({ connection: c }: { connection: ConnectionDetail }) {
  const me = useMe();
  const editable = useCan("connections:write");
  const t = useT();
  const enabled = c.tools.filter((tool) => tool.enabled);
  const writes = enabled.filter((tool) => tool.risk !== "read").length;
  const summary = [
    c.owner
      ? t("conn-summary-owned", { service: c.title, name: personName(c.owner) })
      : t("conn-summary-household", { service: c.title }),
    c.last_used_at
      ? t("conn-summary-usage-last", { assistant: me.assistant, count: c.calls_today, ago: ago(c.last_used_at) })
      : t("conn-summary-usage", { assistant: me.assistant, count: c.calls_today }),
    c.watches ? t("conn-summary-watches", { count: c.watches }) : "",
    t("conn-summary-tools", {
      enabled: enabled.length,
      total: c.tools.length,
      writes,
      confirm: c.confirm_writes ? "yes" : "no",
    }),
  ];
  return (
    <div className="grid gap-10">
      {c.status !== "connected" ? (
        <Panel marked className="grid gap-3 bg-amber-soft/40 sm:grid-cols-[1fr_auto] sm:items-center">
          <div>
            <p className="text-ink">{t("conn-broken", { assistant: me.assistant })}</p>
            {c.status_reason ? (
              <p className="mt-1 font-mono text-xs text-ink-muted">{rendered(c.status_reason)}</p>
            ) : null}
          </div>
          {editable ? (
            <Link
              to="/connections/catalogue"
              search={{ connect: c.kind, replaces: c.id }}
              className={buttonVariants({ className: "justify-self-start" })}
            >
              {t("conn-reconnect-ellipsis")}
            </Link>
          ) : null}
        </Panel>
      ) : null}
      <Lead>{summary.filter(Boolean).join(" ")}</Lead>
      {c.services.length ? (
        <Section title={t("conn-services")}>
          <ul className="grid gap-2 sm:grid-cols-2">
            {c.services.map((s) => (
              <li key={s.name} className="flex min-w-0 items-center gap-2.5 rounded-md border border-rule px-3 py-2">
                <KindMark kind={s.brand ?? c.brand ?? c.kind} className="size-4" label={false} />
                <span className="min-w-0 flex-1 truncate text-ink">
                  {s.brand && s.brand !== c.brand ? kindName(s.brand) : s.name}
                </span>
                {s.handle ? (
                  <code className="shrink-0 font-mono text-[0.85rem] text-ink-muted">@{s.handle}</code>
                ) : (
                  <span className="shrink-0 text-[0.85rem] text-ink-faint">{t("conn-service-unnamed")}</span>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[0.85rem] text-ink-muted">{t("conn-services-hint", { assistant: me.assistant })}</p>
        </Section>
      ) : null}
      <Section title={t("conn-latest-uses")}>
        <ActivityList
          filters={{ connection: c.id }}
          search={{ connection: c.id }}
          limit={5}
          empty={t("conn-never-used", { assistant: me.assistant })}
        />
      </Section>
    </div>
  );
}

export function ConnectionSettings({ connection: c }: { connection: ConnectionDetail }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const notify = useNotify();
  const editable = useCan("connections:write");
  const t = useT();
  const disconnect = useMutation({
    mutationFn: () => api.disconnect(c.id),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: keys.connection(c.id) });
      void queryClient.invalidateQueries({ queryKey: keys.connections });
      notify(t("conn-disconnected", { account: c.account }));
      void navigate({ to: "/connections" });
    },
  });
  if (!editable) return <p className="text-sm text-ink-muted">{t("conn-read-only")}</p>;
  return (
    <div className="grid max-w-2xl gap-10">
      <Section title={t("conn-reconnect")}>
        <p className="mb-4 text-sm text-ink-muted">{t("conn-reconnect-hint")}</p>
        <Link
          to="/connections/catalogue"
          search={{ connect: c.kind, replaces: c.id }}
          className={buttonVariants({ variant: "outline" })}
        >
          {t("conn-reconnect-ellipsis")}
        </Link>
      </Section>
      <Section title={t("conn-disconnect")}>
        <p className="mb-4 text-sm text-ink-muted">{t("conn-disconnect-hint")}</p>
        <Confirm
          trigger={<Button variant="destructive">{t("conn-disconnect-ellipsis")}</Button>}
          title={t("conn-disconnect-title", { account: c.account })}
          confirm={t("conn-disconnect")}
          onConfirm={() => disconnect.mutateAsync()}
        >
          {t("conn-disconnect-consequence")}
        </Confirm>
      </Section>
    </div>
  );
}
