import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CircleAlert, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { type Home, homeQuery, satellitesQuery } from "@/api";
import { Fact, Facts, PageHeader, Panel, RowList, Section } from "@/components/page";
import { RiskTag } from "@/components/risk-tag";
import { Empty, Failure, Loading } from "@/components/states";
import { Status, Tag } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { PresenceMark } from "@/features/people/people";
import { HEALTH, UNKNOWN } from "@/features/system/system-view";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { granularityLabel } from "@/lib/labels";
import { useCan } from "@/lib/session";

/** The home system (Home Assistant): whether it answers, who is where, its rooms, who it knows, and its actions. */
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
      <>
        <PageHeader title={t("house-title")} />
        <Empty hint={t("house-none-hint")} action={configure}>
          {t("house-none")}
        </Empty>
      </>
    );
  return <Loaded home={home.data} configure={configure} />;
}

function Loaded({ home, configure }: { home: Home; configure: ReactNode }) {
  const t = useT();
  const health = home.component.health ? HEALTH[home.component.health] : UNKNOWN;
  return (
    <>
      <PageHeader
        title={t("house-title")}
        meta={
          <>
            {home.component.brand ? <KindMark kind={home.component.brand} className="size-4 text-ink" /> : null}
            <Status tone={health.tone}>{t(health.label)}</Status>
            {home.component.health_detail ? <span>{home.component.health_detail}</span> : null}
          </>
        }
        actions={configure}
      >
        {t("house-lede", { granularity: granularityLabel(home.granularity) })}
      </PageHeader>
      <div className="grid gap-10">
        <Section title={t("house-people")} count={home.people.length}>
          <RowList>
            {home.people.map((p) => (
              <li
                key={p.person.id}
                className="grid gap-x-6 gap-y-1 px-5 py-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto] sm:items-center"
              >
                <Link
                  to="/people/$personId"
                  params={{ personId: p.person.id }}
                  className="truncate text-ink hover:text-ember"
                >
                  {p.person.name}
                </Link>
                <span className="truncate font-mono text-[0.8rem] text-ink-muted">
                  {p.entity ?? t("house-not-tied")}
                  {p.tracker ? ` · ${p.tracker}` : ""}
                </span>
                <PresenceMark presence={p.entity ? p.presence : null} />
              </li>
            ))}
          </RowList>
        </Section>
        <Rooms home={home} />
        {home.residents.length ? (
          <Section title={t("house-residents")} count={home.residents.length}>
            <RowList>
              {home.residents.map((r) => (
                <li key={r.entity} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 px-5 py-3">
                  <span className="min-w-0">
                    <span className="text-ink">{r.name}</span>{" "}
                    <span className="font-mono text-[0.8rem] text-ink-muted">{r.entity}</span>
                  </span>
                  <span className="text-[0.85rem] text-ink-muted">
                    {r.person ? t("house-resident-tied", { name: r.person.name }) : t("house-resident-untied")}
                  </span>
                </li>
              ))}
            </RowList>
          </Section>
        ) : null}
        <Section title={t("house-actions")} count={home.tools.length}>
          {home.tools.length ? (
            <RowList>
              {home.tools.map((tool) => (
                <li
                  key={tool.name}
                  className="grid gap-x-6 gap-y-1 px-5 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
                >
                  <span className="min-w-0">
                    <span className="block font-mono text-[0.85rem] text-ink">{tool.name}</span>
                    <span className="block text-[0.85rem] text-ink-muted">{tool.description}</span>
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
          <Panel>
            <p className="flex items-center gap-2 text-ink">
              <CircleAlert className="size-4 text-amber" aria-hidden="true" />
              {t("house-unplaced", { count: home.unplaced_sensors.length })}
            </p>
            <p className="mt-2 flex flex-wrap gap-1.5">
              {home.unplaced_sensors.map((s) => (
                <Tag key={s}>{s}</Tag>
              ))}
            </p>
          </Panel>
        ) : null}
      </div>
    </>
  );
}

function Rooms({ home }: { home: Home }) {
  const t = useT();
  const satellites = useQuery(satellitesQuery);
  const names = new Map((satellites.data?.paired ?? []).map((s) => [s.id, s.name ?? s.id]));
  if (!home.connected) return null;
  return (
    <Section title={t("house-rooms")} count={home.rooms.length}>
      {home.rooms.length ? (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {home.rooms.map((room) => (
            <Panel as="li" key={room.id} className="grid content-start gap-2">
              <p className="flex items-center justify-between gap-3">
                <span className="truncate text-ink">{room.name}</span>
                {room.occupied === null ? null : (
                  <Status tone={room.occupied ? "accent" : "idle"}>
                    {room.occupied ? t("house-room-occupied") : t("house-room-empty")}
                  </Status>
                )}
              </p>
              <Facts narrow>
                {home.granularity === "person_room" ? ( // only then does the home place people in rooms
                  <Fact term={t("house-room-people")}>
                    {room.people.length ? room.people.map((p) => p.name).join(", ") : t("house-room-nobody")}
                  </Fact>
                ) : null}
                <Fact term={t("house-room-satellites")}>
                  {room.satellites.length ? room.satellites.map((id) => names.get(id) ?? id).join(", ") : "—"}
                </Fact>
              </Facts>
            </Panel>
          ))}
        </ul>
      ) : (
        <Empty>{t("house-rooms-empty")}</Empty>
      )}
    </Section>
  );
}
