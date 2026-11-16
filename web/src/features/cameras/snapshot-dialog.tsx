import { useMutation } from "@tanstack/react-query";
import { Download, RotateCw } from "lucide-react";
import { type ReactElement, useEffect } from "react";
import { api, type MediaDevice } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { FormActions } from "@/components/form-actions";
import { FormDialog } from "@/components/overlay-form";
import { Failure } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { useT } from "@/i18n";
import { deviceName } from "./live-dialog";

/** `salon-2026-11-16-1842.jpg`: the device and the minute it was taken. */
function fileName(device: MediaDevice, at: Date): string {
  const two = (n: number) => String(n).padStart(2, "0");
  const day = `${at.getFullYear()}-${two(at.getMonth() + 1)}-${two(at.getDate())}`;
  return `${device.id}-${day}-${two(at.getHours())}${two(at.getMinutes())}.jpg`;
}

/** A still picture of what a device films, taken when the dialog opens, to look at or keep. */
export function SnapshotDialog({ device, trigger }: { device: MediaDevice; trigger: ReactElement }) {
  const t = useT();
  return (
    <FormDialog trigger={trigger} title={t("cam-picture-title", { name: deviceName(device) })} wide>
      {(close) => <Snapshot device={device} close={close} />}
    </FormDialog>
  );
}

function Snapshot({ device, close }: { device: MediaDevice; close: () => void }) {
  const t = useT();
  const take = useMutation({
    mutationFn: async () => ({ url: URL.createObjectURL(await api.snapshot(device.id)), at: new Date() }),
  });
  const picture = take.data;
  const { mutate } = take;
  useEffect(() => {
    const start = setTimeout(() => mutate()); // once, even when React mounts it twice (strict mode)
    return () => clearTimeout(start);
  }, [mutate]);
  useEffect(() => (picture ? () => URL.revokeObjectURL(picture.url) : undefined), [picture]);
  return (
    <div className="grid gap-4">
      <div className="grid aspect-video place-items-center overflow-hidden rounded-lg bg-paper-sunken">
        {picture ? (
          <img
            src={picture.url}
            alt={t("cam-picture-alt", { name: deviceName(device), room: device.room })}
            className="size-full object-contain"
          />
        ) : take.isPending ? (
          <div className="grid justify-items-center gap-3" role="status">
            <AgentFigure state="thinking" size="md" />
            <p className="text-sm text-ink-muted">{t("cam-taking")}</p>
          </div>
        ) : null}
      </div>
      {take.isError ? <Failure error={take.error} /> : null}
      <FormActions>
        <Button variant="outline" disabled={take.isPending} onClick={() => mutate()}>
          <RotateCw /> {t("cam-picture-again")}
        </Button>
        {picture ? (
          <a
            href={picture.url}
            download={fileName(device, picture.at)}
            className={buttonVariants({ variant: "outline" })}
          >
            <Download /> {t("cam-download")}
          </a>
        ) : null}
        <Button onClick={close}>{t("action-close")}</Button>
      </FormActions>
    </div>
  );
}
