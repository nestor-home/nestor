/**
 * One connection: the service's logo, the account and where it stands; then what one acts on (reconnecting,
 * its tools, who may use it), then what the agent did with it.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Activity, Gauge, RefreshCw, Settings2, Unplug, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { api, type ConnectionDetail, connectionQuery, keys } from "@/api";
import { Ago } from "@/components/ago";
import { CardHead, OpenArrow } from "@/components/card";
import { Confirm } from "@/components/confirm";
import { Crumbs } from "@/components/crumbs";
import { IconTile, OwnerMark, ServiceTile } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { TabNav } from "@/components/tab-nav";
import { Button, buttonVariants } from "@/components/ui/button";
import { ActivityList } from "@/features/journal/activity-list";
import { useT } from "@/i18n";
import { KindMark, kindName } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { rendered } from "@/lib/messages";
import { personName } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { ConnectionStatusMark, needsSomeone } from "./parts";
import { trail } from "./trail";

export function useConnection(id: string) {
  return useQuery(connectionQuery(id));
}

/** The frame of a connection's pages: where it sits, what it is, its tabs. */
export function ConnectionFrame({ id, children }: { id: string; children: ReactNode }) {
  const connection = useConnection(id);
  const t = useT();
  if (connection.isPending) return <Loading lines={4} />;
  if (connection.isError) {
    return (
      <>
        <Crumbs trail={trail(id)} />
        <Failure error={connection.error} retry={() => void connection.refetch()} />
      </>
    );
  }
  const c = connection.data;
  const base = `/connections/${c.id}`;
  return (
    <div>
      <PageHeader
        crumbs={<Crumbs trail={trail(c.account)} />}
        mark={<ServiceTile kind={c.brand ?? c.kind} size="lg" />}
        title={c.account}
        meta={
          <>
            <ConnectionStatusMark status={c.status} />
            <span>{c.title}</span>
            <span className="inline-flex items-center gap-1.5">
              <OwnerMark owner={c.owner} size="xs" />
              {personName(c.owner)}
            </span>
            <span>{t("conn-connected-at", { when: moment(c.created_at) })}</span>
          </>
        }
      />
      <TabNav
        label={t("conn-sections")}
        tabs={[
          { to: base, label: t("conn-tab-overview"), icon: Gauge },
          {
            to: `${base}/tools`,
            label: t("conn-tools"),
            icon: Wrench,
            count: c.tools.filter((tool) => tool.enabled).length,
          },
          { to: `${base}/activity`, label: t("conn-tab-activity"), icon: Activity },
          { to: `${base}/settings`, label: t("conn-tab-settings"), icon: Settings2 },
        ]}
      />
      {children}
    </div>
  );
}

export function ConnectionOverview({ connection: c }: { connection: ConnectionDetail }) {
  const me = useMe();
  const editable = useCan("connections:write");
  const t = useT();
  const enabled = c.tools.filter((tool) => tool.enabled);
  const writes = enabled.filter((tool) => tool.risk !== "read").length;
  return (
    <div className="grid gap-10">
      {needsSomeone(c) ? (
        <div className="surface p-4">
          <CardHead
            mark={<IconTile icon={RefreshCw} tone={c.status === "error" ? "brick" : "amber"} />}
            title={t("conn-broken", { assistant: me.assistant })}
            line={t(c.status === "needs_reauth" ? "conn-fix-reauth" : "conn-fix-error", { assistant: me.assistant })}
          >
            {c.status_reason ? (
              <span className="font-mono text-meta text-ink-muted">{rendered(c.status_reason)}</span>
            ) : null}
            {editable ? (
              <Link
                to="/connections/catalogue"
                search={{ connect: c.kind, replaces: c.id }}
                className={buttonVariants({ size: "sm" })}
              >
                <RefreshCw aria-hidden="true" /> {t("conn-reconnect-ellipsis")}
              </Link>
            ) : null}
          </CardHead>
        </div>
      ) : null}

      <Section title={t("conn-glance")}>
        <ul className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Figure label={t("conn-figure-calls")} value={c.calls_today}>
            {c.last_used_at ? (
              <>
                {t("conn-last-used")} <Ago iso={c.last_used_at} />
              </>
            ) : (
              t("conn-never-used-short")
            )}
          </Figure>
          <li>
            <Link
              to="/connections/$connectionId/tools"
              params={{ connectionId: c.id }}
              className="surface flex h-full flex-col p-4"
            >
              <FigureBody label={t("conn-figure-tools")} value={`${enabled.length} / ${c.tools.length}`}>
                {t("conn-figure-writes", { count: writes })}
              </FigureBody>
            </Link>
          </li>
          <Figure label={t("conn-figure-confirm")} value={c.confirm_writes ? t("conn-yes") : t("conn-no")}>
            {t("conn-confirm-writes-hint")}
          </Figure>
          <Figure label={t("conn-figure-watches")} value={c.watches}>
            {t("conn-figure-watches-note", { count: c.watches })}
          </Figure>
        </ul>
      </Section>

      <Section title={t("conn-who")}>
        {c.owner ? (
          <Link to="/people/$personId" params={{ personId: c.owner.id }} className="group surface block p-4">
            <CardHead
              mark={<OwnerMark owner={c.owner} size="lg" />}
              title={c.owner.name}
              line={t("conn-who-owner", { assistant: me.assistant, name: c.owner.name })}
              aside={<OpenArrow />}
            />
          </Link>
        ) : (
          <div className="surface p-4">
            <CardHead
              mark={<OwnerMark owner={null} size="lg" />}
              title={personName(null)}
              line={t("conn-who-household", { assistant: me.assistant })}
            />
          </div>
        )}
      </Section>

      {c.services.length ? (
        <Section title={t("conn-services")}>
          <p className="-mt-2 mb-4 max-w-[60ch] text-body text-ink-muted">
            {t("conn-services-hint", { assistant: me.assistant })}
          </p>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {c.services.map((s) => (
              <li key={s.name} className="surface flex min-w-0 items-center gap-3 px-4 py-3">
                <KindMark kind={s.brand ?? c.brand ?? c.kind} className="size-5 text-ink" label={false} />
                <span className="min-w-0 flex-1 truncate text-ink">
                  {s.brand && s.brand !== c.brand ? kindName(s.brand) : s.name}
                </span>
                {s.handle ? (
                  <code className="shrink-0 font-mono text-meta text-ink-muted">@{s.handle}</code>
                ) : (
                  <span className="shrink-0 text-meta text-ink-faint">{t("conn-service-unnamed")}</span>
                )}
              </li>
            ))}
          </ul>
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

/** One figure about the account: what it counts, the number in the display face, a line that places it. */
function Figure({ label, value, children }: { label: string; value: ReactNode; children: ReactNode }) {
  return (
    <li className="surface flex flex-col p-4">
      <FigureBody label={label} value={value}>
        {children}
      </FigureBody>
    </li>
  );
}

function FigureBody({ label, value, children }: { label: string; value: ReactNode; children: ReactNode }) {
  return (
    <>
      <span className="text-meta text-ink-muted">{label}</span>
      <span className="mt-1 title-sheet text-ink tabular">{value}</span>
      <span className="mt-1 text-meta text-ink-muted">{children}</span>
    </>
  );
}

export function ConnectionActivity({ id }: { id: string }) {
  const t = useT();
  return (
    <div className="grid gap-10">
      <Section title={t("conn-tab-activity")}>
        <ActivityList
          filters={{ connection: id }}
          search={{ connection: id }}
          limit={20}
          empty={t("conn-no-activity")}
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
  if (!editable) return <Empty>{t("conn-read-only")}</Empty>;
  return (
    <div className="grid gap-10">
      <Section title={t("conn-tab-settings")}>
        <ul className="grid gap-3 lg:grid-cols-2">
          <li className="surface p-4">
            <CardHead mark={<IconTile icon={RefreshCw} />} title={t("conn-reconnect")} line={t("conn-reconnect-hint")}>
              <Link
                to="/connections/catalogue"
                search={{ connect: c.kind, replaces: c.id }}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <RefreshCw aria-hidden="true" /> {t("conn-reconnect-ellipsis")}
              </Link>
            </CardHead>
          </li>
          <li className="surface p-4">
            <CardHead
              mark={<IconTile icon={Unplug} tone="brick" />}
              title={t("conn-disconnect")}
              line={t("conn-disconnect-hint")}
            >
              <Confirm
                trigger={
                  <Button variant="destructive" size="sm">
                    {t("conn-disconnect-ellipsis")}
                  </Button>
                }
                title={t("conn-disconnect-title", { account: c.account })}
                confirm={t("conn-disconnect")}
                onConfirm={() => disconnect.mutateAsync()}
              >
                {t("conn-disconnect-consequence")}
              </Confirm>
            </CardHead>
          </li>
        </ul>
      </Section>
    </div>
  );
}
