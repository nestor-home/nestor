/**
 * "The house": who lives here and where each one is, the rooms and what is in them, what one can watch
 * or call through, and the home system behind it all. People lead to their page, rooms open in place.
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, BookMarked, Plus, RadioTower, Video } from "lucide-react";
import { useState } from "react";
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
import { IconTile, Pebble } from "@/components/marks";
import { SideSheet } from "@/components/overlay-form";
import { PageHeader, Section } from "@/components/page";
import { Empty, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { buttonVariants } from "@/components/ui/button";
import { SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { type RoomNode, roomsOf } from "@/features/home/mind";
import { AddSatelliteButton } from "@/features/satellites/add-satellite";
import { HEALTH, UNKNOWN } from "@/features/system/system-view";
import { RoomSheet, Through } from "@/features/today/room-sheet";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { startOfToday } from "@/lib/dates";
import { deviceName } from "@/lib/labels";
import { useCan, useMe } from "@/lib/session";
import { cn } from "@/lib/utils";
import { HouseView } from "./house-view";

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

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
  const rooms = roomsOf({ people: household, satellites: satellites.data?.paired ?? [], items, home: home.data }, 60);
  const opened = rooms.find((r) => r.key === open) ?? null;
  const devices = (media.data?.devices ?? []).filter((d) => d.can_view || d.can_call || d.off);
  const health = home.data?.component.health ? HEALTH[home.data.component.health] : UNKNOWN;
  const known = memories.data ?? [];
  const latest = [...known].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0];

  return (
    <div>
      <PageHeader
        title={t("space-house")}
        actions={
          canHome && home.data ? (
            <button
              type="button"
              className="surface flex items-center gap-3 px-4 py-2.5"
              onClick={() => setSystem(true)}
            >
              {home.data.component.brand ? (
                <KindMark kind={home.data.component.brand} className="size-5 text-ink" label={false} />
              ) : null}
              <span className="text-left">
                <span className="block text-[0.95rem] font-medium text-ink">{t("hs-system")}</span>
                <Status tone={health.tone}>{t(health.label)}</Status>
              </span>
              <ArrowRight className="ml-2 size-4 text-ink-faint" aria-hidden="true" />
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
                <li key={d.id} className="surface px-4 py-3.5">
                  <div className="flex items-center gap-3">
                    <IconTile icon={d.can_view || d.off ? Video : RadioTower} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-ink">{deviceName(d)}</p>
                      <p className="text-[0.85rem] text-ink-muted">{capital(d.room)}</p>
                    </div>
                    {d.connected ? null : <Status tone="attention">{t("sat-state-offline")}</Status>}
                  </div>
                  <Through device={d} />
                </li>
              ))}
            </ul>
          </Section>
        ) : null}

        {known.length ? (
          <Link to="/memories" className="surface flex items-center gap-4 p-5">
            <IconTile icon={BookMarked} tone="sage" className="size-11" />
            <span className="min-w-0 flex-1">
              <span className="block font-serif text-[1.35rem] leading-tight text-ink">
                {t("hs-memories", { assistant: me.assistant, count: known.length })}
              </span>
              {latest ? (
                <span className="mt-1 line-clamp-1 block text-[0.95rem] text-ink-muted">
                  {t("message-quoted", { text: latest.text })}
                </span>
              ) : null}
            </span>
            <ArrowRight className="size-4 text-ink-faint" aria-hidden="true" />
          </Link>
        ) : null}

        <RoomSheet room={opened} items={items} onClose={() => setOpen(null)} />
        <SideSheet open={system} onOpenChange={setSystem}>
          <SheetHeader className="sr-only">
            <SheetTitle>{t("hs-system")}</SheetTitle>
            <SheetDescription>{t("hs-system")}</SheetDescription>
          </SheetHeader>
          <div className="px-6 pt-10 pb-10">
            <HouseView />
          </div>
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
      <Link to="/people/$personId" params={{ personId: p.id }} className="surface flex h-full flex-col gap-4 p-4">
        <span className="flex items-start justify-between">
          <Pebble name={p.name} away={home === false} className="size-12 text-[1.15rem]" />
          <span className="flex gap-1.5 pt-1">
            {p.channel_accounts.map((c) => (
              <KindMark key={c} kind={c} className="size-4" label={false} />
            ))}
          </span>
        </span>
        <span>
          <span className="block font-serif text-[1.35rem] leading-tight text-ink">{p.name}</span>
          <span className={cn("mt-1 block text-[0.95rem]", home ? "font-medium text-ink" : "text-ink-muted")}>
            {where}
            {p.presence?.since ? (
              <span className="font-normal text-ink-muted">
                {" · "}
                <Ago iso={p.presence.since} />
              </span>
            ) : null}
          </span>
        </span>
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
        className={cn(
          "surface flex h-full w-full flex-col gap-4 p-4 text-left",
          lit && "bg-linear-to-b from-ember-soft to-paper-raised to-70%",
        )}
      >
        <span className="flex items-baseline justify-between gap-3">
          <span className="truncate font-serif text-[1.35rem] leading-tight text-ink">{capital(r.room)}</span>
          {r.active ? (
            <span className="shrink-0 text-[0.85rem] text-ink-muted">{t("hs-room-events", { count: r.active })}</span>
          ) : null}
        </span>
        <span className="flex min-h-7 flex-wrap items-center gap-1.5 text-[0.95rem] text-ink-muted">
          {r.people.map((p) => (
            <Pebble key={p.id} name={p.name} />
          ))}
          {r.people.length ? (
            <span className="ml-1 font-medium text-ink">{r.people.map((p) => p.name).join(", ")}</span>
          ) : r.occupied === null ? (
            t("room-no-sensor")
          ) : (
            t(r.occupied ? "room-someone" : "room-nobody")
          )}
        </span>
        {r.satellites.length ? (
          <span className="mt-auto flex flex-wrap gap-x-4 gap-y-1 border-t border-rule pt-3 text-[0.88rem] text-ink-muted">
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
        ) : null}
      </button>
    </li>
  );
}
