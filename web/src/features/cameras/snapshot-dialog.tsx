import { useMutation } from "@tanstack/react-query";
import { Download, RotateCw } from "lucide-react";
import { type ReactElement, useEffect, useState } from "react";
import { api, type MediaDevice } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { FormActions } from "@/components/form-actions";
import { FormDialog } from "@/components/overlay-form";
import { Failure } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { useT } from "@/i18n";
import { deviceName } from "@/lib/labels";

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
  const take = useMutation({ mutationFn: () => api.snapshot(device.id) });
  const { mutate } = take;
  useEffect(() => {
    const start = setTimeout(() => mutate()); // once, even when React mounts it twice (strict mode)
    return () => clearTimeout(start);
  }, [mutate]);
  const url = useObjectUrl(take.data?.blob);
  return (
    <div className="grid gap-4">
      <div className="grid aspect-video place-items-center overflow-hidden rounded-(--radius-surface) bg-paper-sunken">
        {url ? (
          <img
            src={url}
            alt={t("cam-picture-alt", { name: deviceName(device), room: device.room })}
            className="size-full object-contain"
          />
        ) : take.isPending ? (
          <div className="grid justify-items-center gap-3" role="status">
            <AgentFigure state="thinking" size="md" />
            <p className="text-body text-ink-muted">{t("cam-taking")}</p>
          </div>
        ) : null}
      </div>
      {take.isError ? <Failure error={take.error} /> : null}
      <FormActions>
        <Button variant="outline" disabled={take.isPending} onClick={() => mutate()}>
          <RotateCw /> {t("cam-picture-again")}
        </Button>
        {url ? (
          <a href={url} download={take.data?.name ?? ""} className={buttonVariants({ variant: "outline" })}>
            <Download /> {t("cam-download")}
          </a>
        ) : null}
        <Button onClick={close}>{t("action-close")}</Button>
      </FormActions>
    </div>
  );
}

/** A URL for `blob` while it is shown, revoked when the blob changes or the dialog goes away. */
function useObjectUrl(blob: Blob | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) return;
    const made = URL.createObjectURL(blob);
    setUrl(made);
    return () => {
      URL.revokeObjectURL(made);
      setUrl(null);
    };
  }, [blob]);
  return url;
}
