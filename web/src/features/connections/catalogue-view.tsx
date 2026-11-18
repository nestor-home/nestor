/**
 * The catalogue: every service that can be connected, by what it brings. Accounts bring a person's mail,
 * calendar and files; tool servers bring a service's tools. Connecting opens in a sheet over the grid.
 */
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { type Connector, connectionsQuery, connectorsQuery } from "@/api";
import { Crumbs } from "@/components/crumbs";
import { ServiceTile } from "@/components/marks";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Tag } from "@/components/status";
import { useT } from "@/i18n";
import { authLabel } from "@/lib/labels";
import { useCan } from "@/lib/session";
import { cn } from "@/lib/utils";
import { ConnectSheet } from "./connect-sheet";
import { trail } from "./trail";

export interface CatalogueSearch {
  connect?: string; // the connector whose sheet is open
  replaces?: string; // the broken connection being reconnected
  preset?: string; // the known server picked on the grid
  owner?: string; // whose account it will be, when one comes from a person's page
}

/** A connector found by its address serves tools; the others are a person's or the household's account. */
const servesTools = (c: Connector) => c.auth === "discovered";

export function CatalogueView({
  search,
  onSearch,
}: {
  search: CatalogueSearch;
  onSearch: (search: CatalogueSearch) => void;
}) {
  const t = useT();
  const connectors = useQuery(connectorsQuery);
  const connections = useQuery(connectionsQuery);
  const canConnect = useCan("connections:write");
  const plugged = (kind: string) => (connections.data ?? []).filter((c) => c.kind === kind).length;
  const accounts = (connectors.data ?? []).filter((c) => !servesTools(c));
  const servers = (connectors.data ?? []).filter(servesTools);

  return (
    <div>
      <PageHeader crumbs={<Crumbs trail={trail(t("conn-catalogue"))} />} title={t("conn-catalogue")}>
        {canConnect ? t("conn-catalogue-lede") : t("conn-catalogue-read-only")}
      </PageHeader>
      <div className="grid gap-10">
        {connectors.isPending ? (
          <Loading lines={3} />
        ) : connectors.isError ? (
          <Failure error={connectors.error} retry={() => void connectors.refetch()} />
        ) : connectors.data.length === 0 ? (
          <Empty>{t("conn-no-connector")}</Empty>
        ) : (
          <>
            {accounts.length ? (
              <Section title={t("conn-group-accounts")}>
                <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {accounts.map((c) => (
                    <ServiceCard
                      key={c.kind}
                      connector={c}
                      accounts={plugged(c.kind)}
                      onConnect={
                        canConnect
                          ? () => onSearch({ ...(search.owner ? { owner: search.owner } : {}), connect: c.kind })
                          : undefined
                      }
                    />
                  ))}
                </ul>
              </Section>
            ) : null}
            {servers.map((c) => (
              <Section key={c.kind} id={`tools-${c.kind}`} title={servers.length > 1 ? c.title : t("conn-group-tools")}>
                <p className="-mt-2 mb-4 max-w-[60ch] text-body text-ink-muted">{c.description}</p>
                <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
                  {c.presets.map((p) => (
                    <li key={p.name}>
                      <Opens
                        onOpen={
                          canConnect
                            ? () =>
                                onSearch({
                                  ...(search.owner ? { owner: search.owner } : {}),
                                  connect: c.kind,
                                  preset: p.name,
                                })
                            : undefined
                        }
                        className="flex h-full w-full items-center gap-3 p-3 text-left"
                      >
                        <ServiceTile kind={p.brand ?? c.brand ?? c.kind} />
                        <span className="min-w-0 truncate text-body font-medium text-ink">{p.name}</span>
                      </Opens>
                    </li>
                  ))}
                  <li>
                    <Opens
                      onOpen={
                        canConnect
                          ? () => onSearch({ ...(search.owner ? { owner: search.owner } : {}), connect: c.kind })
                          : undefined
                      }
                      className="flex h-full w-full items-center gap-3 p-3 text-left"
                    >
                      <ServiceTile kind={c.brand ?? c.kind} />
                      <span className="min-w-0">
                        <span className="block truncate text-body font-medium text-ink">{t("conn-other-server")}</span>
                        <span className="block truncate text-meta text-ink-muted">
                          {plugged(c.kind) ? t("conn-accounts-count", { count: plugged(c.kind) }) : c.title}
                        </span>
                      </span>
                    </Opens>
                  </li>
                </ul>
              </Section>
            ))}
          </>
        )}
      </div>
      <ConnectSheet
        kind={search.connect}
        replaces={search.replaces}
        preset={search.preset}
        owner={search.owner}
        onClose={() => onSearch({})}
      />
    </div>
  );
}

/** A card that opens the connect sheet, or stands still for who may only look. */
function Opens({
  onOpen,
  className,
  children,
}: {
  onOpen: (() => void) | undefined;
  className: string;
  children: ReactNode;
}) {
  if (!onOpen) return <div className={cn("surface", className)}>{children}</div>;
  return (
    <button type="button" onClick={onOpen} className={cn("surface", className)}>
      {children}
    </button>
  );
}

function ServiceCard({
  connector: c,
  accounts,
  onConnect,
}: {
  connector: Connector;
  accounts: number;
  onConnect: (() => void) | undefined;
}) {
  const t = useT();
  return (
    <li>
      <Opens onOpen={onConnect} className="flex h-full w-full flex-col gap-3 p-4 text-left">
        <span className="flex w-full items-center justify-between gap-3">
          <ServiceTile kind={c.brand ?? c.kind} size="lg" />
          {c.auth === "oauth2" && !c.oauth?.registered ? (
            <Tag tone="attention">{t("conn-client-to-create")}</Tag>
          ) : accounts ? (
            <Tag>{t("conn-accounts-count", { count: accounts })}</Tag>
          ) : null}
        </span>
        <span className="flex-1">
          <span className="block title-card text-ink">{c.title}</span>
          <span className="mt-1.5 block text-body text-ink-muted">{c.description}</span>
        </span>
        <span className="text-meta text-ink-muted">
          {authLabel(c.auth)}
          {c.inbound.length ? ` · ${t("conn-feeds-watches")}` : ""}
        </span>
      </Opens>
    </li>
  );
}
