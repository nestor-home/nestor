import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CircleAlert, House, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { type Home, homeQuery } from "@/api";
import { CardHead } from "@/components/card";
import { BrandTile, Pebble } from "@/components/marks";
import { SheetPanel } from "@/components/overlay-form";
import { Panel, RowList, Section } from "@/components/page";
import { RiskTag } from "@/components/risk-tag";
import { Empty, Failure, Loading } from "@/components/states";
import { HealthStatus, Tag } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { PresenceMark } from "@/features/people/people";
import { useT } from "@/i18n";
import { brandName, brandOf } from "@/lib/brands";
import { granularityLabel } from "@/lib/labels";
import { useCan } from "@/lib/session";

/**
 * The home system (Home Assistant), as a sheet opened from The house: whether it answers, how finely it tells
 * who is where, the people tied to its entities, what the agent may do through it and at which risk, and the
 * way to its settings.
 */
export function HouseSheet() {
  const t = useT();
  const home = useQuery(homeQuery);
  const canConfigure = useCan("config:manage");
  const configure = canConfigure ? (
    <Link to="/config/$section" params={{ section: "home" }} className={buttonVariants({ variant: "outline" })}>
      {t("house-configure")}
    </Link>
  ) : null;
  if (!home.data)
    return (
      <SheetPanel icon={House} kind={t("hs-system")} title={t("hs-system")}>
        {home.isPending ? (
          <Loading lines={4} />
        ) : home.isError ? (
          <Failure error={home.error} retry={() => void home.refetch()} />
        ) : (
          <Empty hint={t("house-none-hint")} action={configure}>
            {t("house-none")}
          </Empty>
        )}
      </SheetPanel>
    );
  return <Loaded home={home.data} configure={configure} />;
}

function Loaded({ home, configure }: { home: Home; configure: ReactNode }) {
  const t = useT();
  const brand = brandOf(home.component.brand);
  const tied = new Set(home.people.map((p) => p.entity).filter(Boolean));
  const strangers = home.residents.filter((r) => !tied.has(r.entity));
  return (
    <SheetPanel
      mark={brand ? <BrandTile brand={brand} size="sm" /> : undefined}
      icon={House}
      kind={t("hs-system")}
      title={brand ? brandName(brand) : home.component.name}
      description={<HealthStatus health={home.component.health} />}
      actions={configure}
    >
      <div className="grid gap-2">
        {home.component.health_detail ? (
          <p className="text-body text-ink-muted">{home.component.health_detail}</p>
        ) : null}
        <p className="text-body text-ink">{t("house-lede", { granularity: granularityLabel(home.granularity) })}</p>
      </div>

      <Section level={3} title={t("house-people")} count={home.people.length}>
        <ul className="grid gap-2">
          {home.people.map((p) => (
            <li key={p.person.id}>
              <Link to="/people/$personId" params={{ personId: p.person.id }} className="surface block px-4 py-3">
                <CardHead
                  mark={<Pebble name={p.person.name} away={!p.entity || p.presence?.home !== true} size="lg" />}
                  title={p.person.name}
                  line={
                    <span className="font-mono text-meta">
                      {p.entity ?? t("house-not-tied")}
                      {p.tracker ? ` · ${p.tracker}` : ""}
                    </span>
                  }
                  aside={<PresenceMark presence={p.entity ? p.presence : null} />}
                />
              </Link>
            </li>
          ))}
        </ul>
        {strangers.length ? (
          <p className="mt-3 text-body text-ink-muted">
            {t("house-strangers", { count: strangers.length, names: strangers.map((r) => r.name).join(", ") })}
          </p>
        ) : null}
      </Section>

      <Section level={3} title={t("house-actions")} count={home.tools.length}>
        {home.tools.length ? (
          <RowList>
            {home.tools.map((tool) => (
              <li key={tool.name} className="grid gap-2 px-4 py-3">
                <span className="min-w-0">
                  <span className="block font-mono text-meta text-ink">{tool.name}</span>
                  <span className="block text-body text-ink-muted">{tool.description}</span>
                </span>
                <span className="flex flex-wrap gap-1.5">
                  <RiskTag risk={tool.risk} />
                  {tool.confirmed_when ? <Tag icon={ShieldCheck}>{t("house-action-confirmed-when")}</Tag> : null}
                </span>
              </li>
            ))}
          </RowList>
        ) : (
          <Empty hint={t("house-actions-empty-hint")}>{t("house-actions-empty")}</Empty>
        )}
      </Section>

      {home.unplaced_sensors.length ? (
        <Panel className="p-4">
          <p className="flex items-start gap-2 text-body text-ink">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber" aria-hidden="true" />
            {t("house-unplaced", { count: home.unplaced_sensors.length })}
          </p>
          <p className="mt-2.5 flex flex-wrap gap-1.5">
            {home.unplaced_sensors.map((s) => (
              <Tag key={s}>{s}</Tag>
            ))}
          </p>
        </Panel>
      ) : null}
    </SheetPanel>
  );
}
