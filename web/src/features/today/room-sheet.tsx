import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, Camera, Eye, Phone, RadioTower, Video } from "lucide-react";
import { type JournalItem, type MediaDevice, mediaDevicesQuery } from "@/api";
import { Ago } from "@/components/ago";
import { IconTile, Pebble } from "@/components/marks";
import { SheetPanel, SideSheet } from "@/components/overlay-form";
import { Empty } from "@/components/states";
import { Status } from "@/components/status";
import { Button } from "@/components/ui/button";
import { LiveDialog } from "@/features/cameras/live-dialog";
import { SnapshotDialog } from "@/features/cameras/snapshot-dialog";
import type { RoomNode } from "@/features/home/mind";
import { useT } from "@/i18n";
import { hourMinute } from "@/lib/dates";
import { deviceName } from "@/lib/labels";
import { say } from "@/lib/messages";
import { useCan } from "@/lib/session";

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** A room, opened: who is there, its devices and what one can do through them, and its day. */
export function RoomSheet({
  room,
  items,
  onClose,
}: {
  room: RoomNode | null;
  items: readonly JournalItem[];
  onClose: () => void;
}) {
  return (
    <SideSheet open={Boolean(room)} onOpenChange={(open) => !open && onClose()}>
      {room ? <Room room={room} items={items} /> : null}
    </SideSheet>
  );
}

function Room({ room: r, items }: { room: RoomNode; items: readonly JournalItem[] }) {
  const t = useT();
  const media = useQuery({ ...mediaDevicesQuery, enabled: useCan("media:read") });
  const devices = new Map((media.data?.devices ?? []).map((d) => [d.id, d]));
  const day = r.journal ? items.filter((i) => i.room === r.journal).slice(0, 6) : [];
  const who = r.people.length
    ? t("room-with", { people: r.people.map((p) => p.name).join(", "), count: r.people.length })
    : r.occupied === null
      ? t("room-no-sensor")
      : t(r.occupied ? "room-someone" : "room-nobody");
  return (
    <SheetPanel title={capital(r.room)} description={who}>
      {r.people.length ? (
        <ul className="grid gap-2">
          {r.people.map((p) => (
            <li key={p.id}>
              <Link
                to="/people/$personId"
                params={{ personId: p.id }}
                className="surface flex items-center gap-3 px-4 py-3"
              >
                <Pebble name={p.name} size="lg" />
                <span className="min-w-0 flex-1">
                  <span className="block text-ink">{p.name}</span>
                  {p.presence?.since ? (
                    <span className="block text-meta text-ink-muted">
                      {t("room-since")} <Ago iso={p.presence.since} />
                    </span>
                  ) : null}
                </span>
                <ArrowRight className="size-4 text-ink-faint" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}

      <div>
        <h3 className="mb-3 title-sub text-ink">{t("room-devices")}</h3>
        {r.satellites.length ? (
          <ul className="grid gap-2">
            {r.satellites.map((s) => (
              <li key={s.id} className="surface px-4 py-3.5">
                <div className="flex items-center gap-3">
                  <IconTile icon={s.films ? Video : RadioTower} />
                  <Link
                    to="/satellites/$satelliteId"
                    params={{ satelliteId: s.id }}
                    className="min-w-0 flex-1 hover:underline"
                  >
                    <span className="block text-ink">{deviceName(s)}</span>
                    <span className="block text-meta text-ink-muted">{s.model}</span>
                  </Link>
                  {s.connected === false ? (
                    <Status tone="attention">{t("sat-state-offline")}</Status>
                  ) : (
                    <Status tone="ok">{t("sat-state-connected")}</Status>
                  )}
                </div>
                <Through device={devices.get(s.id)} />
              </li>
            ))}
          </ul>
        ) : (
          <Empty>{t("room-no-device")}</Empty>
        )}
      </div>

      {r.journal ? (
        <div>
          <div className="mb-3 flex items-baseline justify-between gap-4">
            <h3 className="title-sub text-ink">{t("room-today")}</h3>
            <Link
              to="/journal"
              search={{ room: r.journal }}
              className="inline-flex items-center gap-1 text-body text-ink-muted hover:text-ink"
            >
              {t("home-all-journal")} <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
          </div>
          {day.length ? (
            <ol className="grid gap-2.5">
              {day.map((i) => (
                <li key={i.id} className="grid grid-cols-[3rem_1fr] gap-x-3 text-body">
                  <time dateTime={i.at} className="text-ink-muted tabular">
                    {hourMinute(i.at)}
                  </time>
                  <span className="min-w-0 text-ink">{i.detail_text || say(i)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <Empty>{t("room-quiet-today")}</Empty>
          )}
        </div>
      ) : null}
    </SheetPanel>
  );
}

/** What one may do through a device from here: watch, take a picture, call. Each opens over the room. */
export function Through({ device: d }: { device: MediaDevice | undefined }) {
  const t = useT();
  if (!d || (!d.can_view && !d.can_call && !d.off)) return null;
  const name = deviceName(d);
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-rule pt-3">
      {d.can_view ? (
        <LiveDialog
          device={d}
          purpose="view"
          trigger={
            <Button variant="outline" size="sm" disabled={!d.connected} aria-label={t("cam-view-for", { name })}>
              <Eye /> {t("cam-view")}
            </Button>
          }
        />
      ) : null}
      {d.can_view ? (
        <SnapshotDialog
          device={d}
          trigger={
            <Button variant="outline" size="sm" disabled={!d.connected} aria-label={t("cam-picture-for", { name })}>
              <Camera /> {t("cam-picture")}
            </Button>
          }
        />
      ) : null}
      {d.can_call ? (
        <LiveDialog
          device={d}
          purpose="call"
          trigger={
            <Button variant="outline" size="sm" disabled={!d.connected} aria-label={t("cam-call-for", { name })}>
              <Phone /> {t("cam-call")}
            </Button>
          }
        />
      ) : null}
      {d.off ? <Status tone="idle">{t("cam-off-reason", { off: d.off })}</Status> : null}
    </div>
  );
}
