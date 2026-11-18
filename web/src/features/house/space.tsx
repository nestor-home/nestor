/**
 * "The house": who lives here and where each one is, the rooms and what is in them, what one can watch
 * or call through, and the home system behind it all. People lead to their page, rooms open in place.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { BookMarked, DoorOpen, Plus, RadioTower, Video } from "lucide-react";
import { useMemo, useState } from "react";
import {
  homeQuery,
  journalLatestQuery,
  mediaDevicesQuery,
  memoriesQuery,
  type Person,
  peopleQuery,
  satellitesQuery,
} from "@/api";
import { Ago } from "@/components/ago";
import { CardHead, OpenArrow, TILE_CARD, TileCard } from "@/components/card";
import { Avatar, IconTile, ServiceTile } from "@/components/marks";
import { SideSheet } from "@/components/overlay-form";
import { PageHeader, Section } from "@/components/page";
import { Empty, Loading } from "@/components/states";
import { HealthStatus, Status } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { AddSatelliteButton } from "@/features/satellites/add-satellite";
import { type RoomNode, roomsOf } from "@/features/today/mind";
import { RoomSheet, Through } from "@/features/today/room-sheet";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { startOfToday } from "@/lib/dates";
import { deviceName } from "@/lib/labels";
import { useCan, useMe } from "@/lib/session";
import { capital, cn } from "@/lib/utils";
import { HouseSheet } from "./house-view";

export function HouseSpace() {
  const t = useT();
  const me = useMe();
  const canHome = useCan("home:read");
  const people = useQuery({ ...peopleQuery, enabled: useCan("people:read") });
  const satellites = useQuery({ ...satellitesQuery, enabled: useCan("satellites:read") });
  const home = useQuery({ ...homeQuery, enabled: canHome });
  const media = useQuery({ ...mediaDevicesQuery, enabled: useCan("media:read") });
  const day = useQuery({ ...journalLatestQuery({ from: startOfToday() }, 200), enabled: useCan("journal:read") });
  const memories = useQuery({ ...memoriesQuery({}), enabled: useCan("memories:read") });
  const canConfigure = useCan("config:manage");
  const canPair = useCan("satellites:write");
  const [open, setOpen] = useState<string | null>(null);
  const [system, setSystem] = useState(false);

  const household = people.data ?? [];
  const items = day.data?.items ?? [];
  const rooms = useMemo(
    () =>
      roomsOf(
        {
          people: people.data ?? [],
          satellites: satellites.data?.paired ?? [],
          items: day.data?.items ?? [],
          home: home.data,
        },
        60,
      ),
    [people.data, satellites.data, day.data, home.data],
  );
  const opened = rooms.find((r) => r.key === open) ?? null;
  const devices = (media.data?.devices ?? []).filter((d) => d.can_view || d.can_call || d.off);
  const known = memories.data ?? [];
  const latest = known.reduce<(typeof known)[number] | undefined>(
    (last, m) => (last && last.updated_at >= m.updated_at ? last : m),
    undefined,
  );

  return (
    <div>
      <PageHeader
        title={t("space-house")}
        actions={
          canHome && !home.isPending ? (
            <button type="button" className="group surface px-4 py-2.5 text-left" onClick={() => setSystem(true)}>
              <CardHead
                mark={
                  home.data?.component.brand ? <ServiceTile kind={home.data.component.brand} size="sm" /> : undefined
                }
                title={t("hs-system")}
                line={
                  home.data ? (
                    <HealthStatus health={home.data.component.health} />
                  ) : home.isError ? (
                    <HealthStatus health={null} />
                  ) : (
                    t("house-none")
                  )
                }
                aside={<OpenArrow />}
              />
            </button>
          ) : undefined
        }
      >
        {t("hs-lede", { assistant: me.assistant })}
      </PageHeader>
      <div className="grid gap-10">
        <Section
          title={t("hs-people")}
          count={household.length}
          aside={
            canConfigure ? (
              <Link
                to="/config/$section"
                params={{ section: "household" }}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <Plus /> {t("hs-add-person")}
              </Link>
            ) : undefined
          }
        >
          {people.isPending ? (
            <Loading lines={2} />
          ) : household.length ? (
            <ul className="grid grid-cols-2 gap-3 xl:grid-cols-4">
              {household.map((p) => (
                <PersonCard key={p.id} person={p} />
              ))}
            </ul>
          ) : (
            <Empty>{t("people-empty")}</Empty>
          )}
        </Section>

        <Section title={t("hs-rooms")} count={rooms.length} aside={canPair ? <AddSatelliteButton /> : undefined}>
          {rooms.length ? (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {rooms.map((r) => (
                <RoomCard key={r.key} room={r} onOpen={() => setOpen(r.key)} />
              ))}
            </ul>
          ) : (
            <Empty>{t("hs-rooms-empty")}</Empty>
          )}
        </Section>

        {media.data && !media.data.available ? (
          <Section title={t("hs-media")}>
            <Empty hint={t("hs-media-off-hint")}>{t("hs-media-off")}</Empty>
          </Section>
        ) : null}
        {devices.length ? (
          <Section title={t("hs-media")} count={devices.length}>
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {devices.map((d) => (
                <li key={d.id} className="surface p-4">
                  <CardHead
                    mark={<IconTile icon={d.can_view || d.off ? Video : RadioTower} />}
                    title={deviceName(d)}
                    line={capital(d.room)}
                    aside={d.connected ? null : <Status tone="attention">{t("sat-state-offline")}</Status>}
                  />
                  <Through device={d} />
                </li>
              ))}
            </ul>
          </Section>
        ) : null}

        {known.length ? (
          <Link to="/memories" className="group surface block p-4">
            <CardHead
              mark={<IconTile icon={BookMarked} tone="sage" />}
              title={t("hs-memories", { assistant: me.assistant, count: known.length })}
              line={latest ? <span className="line-clamp-1">{t("message-quoted", { text: latest.text })}</span> : null}
              aside={<OpenArrow />}
            />
          </Link>
        ) : null}

        <RoomSheet room={opened} items={items} onClose={() => setOpen(null)} />
        <SideSheet open={system} onOpenChange={setSystem}>
          <HouseSheet />
        </SideSheet>
      </div>
    </div>
  );
}

/** A member of the household: where they are, how the agent reaches them. */
function PersonCard({ person: p }: { person: Person }) {
  const t = useT();
  const home = p.presence?.home;
  const where =
    home == null
      ? t("people-presence-unknown")
      : home
        ? p.presence?.room
          ? capital(p.presence.room)
          : t("people-presence-home")
        : t("people-presence-away");
  return (
    <li>
      <Link to="/people/$personId" params={{ personId: p.id }} className={TILE_CARD}>
        <TileCard
          marks={<Avatar name={p.name} away={home === false} size="lg" />}
          aside={p.channel_accounts.map((c) => <KindMark key={c} kind={c} className="text-ink-muted" label={false} />)}
          title={p.name}
          line={
            <>
              <span className={home ? "font-medium text-ink" : undefined}>{where}</span>
              {p.presence?.since ? (
                <>
                  {" · "}
                  <Ago iso={p.presence.since} />
                </>
              ) : null}
            </>
          }
        />
      </Link>
    </li>
  );
}

/** A room: warm when someone is in it, with who and which devices. It opens in place. */
function RoomCard({ room: r, onOpen }: { room: RoomNode; onOpen: () => void }) {
  const t = useT();
  const lit = r.people.length > 0 || r.occupied === true;
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className={cn(TILE_CARD, lit && "bg-linear-to-b from-ember-soft to-paper-raised to-70%")}
      >
        <TileCard
          marks={
            r.people.length ? (
              <span className="flex -space-x-1.5">
                {r.people.map((p) => (
                  <Avatar key={p.id} name={p.name} />
                ))}
              </span>
            ) : (
              <IconTile icon={DoorOpen} size="sm" />
            )
          }
          aside={r.active ? t("hs-room-events", { count: r.active }) : null}
          title={capital(r.room)}
          line={
            r.people.length ? (
              <span className="font-medium text-ink">{r.people.map((p) => p.name).join(", ")}</span>
            ) : r.occupied === null ? (
              t("room-no-sensor")
            ) : (
              t(r.occupied ? "room-someone" : "room-nobody")
            )
          }
          foot={
            r.satellites.length ? (
              <span className="flex flex-wrap gap-x-4 gap-y-1">
                {r.satellites.map((s) => {
                  const Icon = s.films ? Video : RadioTower;
                  return (
                    <span key={s.id} className="inline-flex items-center gap-1.5">
                      <Icon className={cn("size-4", s.connected === false && "text-brick")} aria-hidden="true" />
                      {deviceName(s)}
                    </span>
                  );
                })}
              </span>
            ) : null
          }
        />
      </button>
    </li>
  );
}
