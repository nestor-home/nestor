import { useQuery } from "@tanstack/react-query";
import { Camera, Eye, Phone } from "lucide-react";
import { type MediaDevice, mediaDevicesQuery } from "@/api";
import { RowList } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { useCan, useMe } from "@/lib/session";
import { deviceName, LiveDialog } from "./live-dialog";
import { SnapshotDialog } from "./snapshot-dialog";

/** The devices one may watch or call through, each with what one may do: no picture until asked. */
export function CamerasList() {
  const t = useT();
  const me = useMe();
  const devices = useQuery(mediaDevicesQuery);
  if (devices.isPending) return <Loading lines={3} />;
  if (devices.isError) return <Failure error={devices.error} retry={() => void devices.refetch()} />;
  if (!devices.data.available) return <Empty hint={t("cam-off-hint")}>{t("cam-off")}</Empty>;
  if (!devices.data.devices.length)
    return <Empty hint={t("cam-empty-hint", { assistant: me.assistant })}>{t("cam-empty")}</Empty>;
  return (
    <RowList>
      {devices.data.devices.map((d) => (
        <DeviceRow key={d.id} device={d} />
      ))}
    </RowList>
  );
}

function DeviceRow({ device: d }: { device: MediaDevice }) {
  const t = useT();
  const view = useCan("media:view") && d.can_view;
  const call = useCan("media:call") && d.can_call;
  const name = deviceName(d);
  return (
    <li className="grid gap-x-6 gap-y-3 px-5 py-3.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div className="min-w-0">
        <p className="[overflow-wrap:anywhere] text-ink">{name}</p>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-ink-muted">
          <span>{t("sat-room", { room: d.room })}</span>
          {d.connected ? (
            <Status tone="ok">{t("sat-state-connected")}</Status>
          ) : (
            <Status tone="attention">{t("sat-state-offline")}</Status>
          )}
          {view ? null : <span>{t("cam-call-only")}</span>}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {view ? (
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
        {call ? (
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
        {view ? (
          <SnapshotDialog
            device={d}
            trigger={
              <Button variant="outline" size="sm" disabled={!d.connected} aria-label={t("cam-picture-for", { name })}>
                <Camera /> {t("cam-picture")}
              </Button>
            }
          />
        ) : null}
      </div>
    </li>
  );
}
