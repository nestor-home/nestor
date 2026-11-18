import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CircleAlert, House, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { type Home, homeQuery } from "@/api";
import { BrandTile, IconTile, Pebble } from "@/components/marks";
import { RowList } from "@/components/page";
import { RiskTag } from "@/components/risk-tag";
import { Empty, Failure, Loading } from "@/components/states";
import { Status, Tag } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { PresenceMark } from "@/features/people/people";
import { HEALTH, UNKNOWN } from "@/features/system/system-view";
import { useT } from "@/i18n";
import { brandName, brandOf } from "@/lib/brands";
import { granularityLabel } from "@/lib/labels";
import { useCan } from "@/lib/session";

/**
 * The home system (Home Assistant), as a sheet opened from The house: whether it answers, how finely it tells
 * who is where, the people tied to its entities, what the agent may do through it and at which risk, and the
 * way to its settings.
 */
export function HouseView() {
  const t = useT();
  const home = useQuery(homeQuery);
  const canConfigure = useCan("config:manage");
  const configure = canConfigure ? (
    <Link to="/config/$section" params={{ section: "home" }} className={buttonVariants({ variant: "outline" })}>
      {t("house-configure")}
    </Link>
  ) : null;
  if (home.isPending) return <Loading lines={4} />;
  if (home.isError) return <Failure error={home.error} retry={() => void home.refetch()} />;
  if (!home.data)
    return (
      <Empty hint={t("house-none-hint")} action={configure}>
        {t("house-none")}
      </Empty>
    );
  return <Loaded home={home.data} configure={configure} />;
}

function Part({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-3 flex items-baseline gap-2 text-[1.15rem] text-ink">
        {title}
        {count ? <span className="text-[0.85rem] text-ink-muted tabular">{count}</span> : null}
      </h3>
      {children}
    </section>
  );
}

function Loaded({ home, configure }: { home: Home; configure: ReactNode }) {
  const t = useT();
  const health = home.component.health ? HEALTH[home.component.health] : UNKNOWN;
  const brand = brandOf(home.component.brand);
  const tied = new Set(home.people.map((p) => p.entity).filter(Boolean));
  const strangers = home.residents.filter((r) => !tied.has(r.entity));
  return (
    <div className="grid gap-8">
      <header className="grid gap-4">
        <div className="flex items-center gap-4">
          {brand ? <BrandTile brand={brand} className="size-12" /> : <IconTile icon={House} className="size-12" />}
          <div className="min-w-0 flex-1">
            <p className="font-serif text-[1.6rem] leading-snug text-ink">
              {brand ? brandName(brand) : home.component.name}
            </p>
            <Status tone={health.tone}>{t(health.label)}</Status>
          </div>
        </div>
        {home.component.health_detail ? (
          <p className="text-[0.95rem] text-ink-muted">{home.component.health_detail}</p>
        ) : null}
        <p className="text-[0.98rem] text-ink">
          {t("house-lede", { granularity: granularityLabel(home.granularity) })}
        </p>
        {configure ? <div>{configure}</div> : null}
      </header>

      <Part title={t("house-people")} count={home.people.length}>
        <ul className="grid gap-2">
          {home.people.map((p) => (
            <li key={p.person.id}>
              <Link
                to="/people/$personId"
                params={{ personId: p.person.id }}
                className="surface flex items-center gap-3 px-4 py-3"
              >
                <Pebble
                  name={p.person.name}
                  away={!p.entity || p.presence?.home !== true}
                  className="size-9 text-[0.9rem]"
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-ink">{p.person.name}</span>
                  <span className="block truncate font-mono text-[0.78rem] text-ink-muted">
                    {p.entity ?? t("house-not-tied")}
                    {p.tracker ? ` · ${p.tracker}` : ""}
                  </span>
                </span>
                <PresenceMark presence={p.entity ? p.presence : null} />
              </Link>
            </li>
          ))}
        </ul>
        {strangers.length ? (
          <p className="mt-3 text-[0.92rem] text-ink-muted">
            {t("house-strangers", { count: strangers.length, names: strangers.map((r) => r.name).join(", ") })}
          </p>
        ) : null}
      </Part>

      <Part title={t("house-actions")} count={home.tools.length}>
        {home.tools.length ? (
          <RowList>
            {home.tools.map((tool) => (
              <li key={tool.name} className="grid gap-2 px-4 py-3">
                <span className="min-w-0">
                  <span className="block font-mono text-[0.85rem] [overflow-wrap:anywhere] text-ink">{tool.name}</span>
                  <span className="block text-[0.9rem] text-ink-muted">{tool.description}</span>
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
      </Part>

      {home.unplaced_sensors.length ? (
        <div className="surface p-4">
          <p className="flex items-start gap-2 text-[0.95rem] text-ink">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber" aria-hidden="true" />
            {t("house-unplaced", { count: home.unplaced_sensors.length })}
          </p>
          <p className="mt-2.5 flex flex-wrap gap-1.5">
            {home.unplaced_sensors.map((s) => (
              <Tag key={s} className="[overflow-wrap:anywhere]">
                {s}
              </Tag>
            ))}
          </p>
        </div>
      ) : null}
    </div>
  );
}
