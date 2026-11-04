/**
 * A satellite's newer software, from its page: a button at the top says so, and opens a dialog of its
 * own (the device's mark on an ink band, never Nestor's figure) with what that version changes (the
 * notes the device found at its source, opened by the browser), what installing it does, and the
 * install itself. The dialog is the confirmation: it says everything the person is agreeing to.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleArrowUp, ExternalLink, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { api, keys, messageOf, type Satellite } from "@/api";
import { useNotify } from "@/components/notices";
import { Button } from "@/components/ui/button";
import { UpdateDialog } from "@/components/update-dialog";
import { useT } from "@/i18n";
import { useCan } from "@/lib/session";
import { DeviceMark } from "./device-mark";

/** At the top of a satellite's page, while it has a newer version, installs one or failed to. */
export function SatelliteUpdateButton({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const found = s.update;
  if (!s.can_update || !found?.version || found.state === "current") return null;
  const label = {
    available: t("sat-update-button"),
    installing: t("sat-update-button-installing"),
    failed: t("sat-update-button-failed"),
  }[found.state];
  return (
    <>
      <Button
        variant={found.state === "available" ? "accent" : found.state === "failed" ? "destructive" : "outline"}
        size="sm"
        onClick={() => setOpen(true)}
      >
        {found.state === "installing" ? (
          <LoaderCircle className="animate-spin" aria-hidden="true" />
        ) : found.state === "failed" ? (
          <CircleAlert aria-hidden="true" />
        ) : (
          <CircleArrowUp aria-hidden="true" />
        )}
        {label}
      </Button>
      <SatelliteUpdate satellite={s} open={open} onOpenChange={setOpen} />
    </>
  );
}

function SatelliteUpdate({
  satellite: s,
  open,
  onOpenChange,
}: {
  satellite: Satellite;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
  const canUpdate = useCan("satellites:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const update = useMutation({
    mutationFn: () => api.updateSatellite(s.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.satellites });
      notify(t("sat-update-asked", { id: s.name ?? s.id }));
    },
  });
  const { state, version, notes } = s.update ?? { state: "current", version: null, notes: null };
  if (!version) return null;
  const running = s.software.version;
  const name = s.name ?? s.id;
  return (
    <UpdateDialog
      open={open}
      onOpenChange={onOpenChange}
      tone="ink"
      mark={
        <span className="mb-5 grid size-20 place-items-center rounded-2xl border border-rule bg-paper-raised text-ink shadow-sm">
          <DeviceMark brand={s.brand} capabilities={s.capabilities.map((c) => c.name)} className="size-10" />
        </span>
      }
      title={t("sat-update-title", { name, version })}
      description={t("sat-update-description")}
      running={running}
      latest={version}
      aside={s.software.name}
      footer={
        state === "installing" ? (
          <p role="status" className="flex items-center gap-2 text-sm text-ink">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            {t("sat-update-installing", { version })}
          </p>
        ) : state === "available" && canUpdate ? (
          <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
            {update.error || s.connected === false ? (
              <p className="mr-auto text-xs text-ink-muted">
                {update.error ? messageOf(update.error) : t("sat-update-offline")}
              </p>
            ) : null}
            <Button
              variant="accent"
              onClick={() => update.mutate()}
              disabled={update.isPending || s.connected === false}
            >
              {update.isPending ? "…" : t("sat-update-action", { version })}
            </Button>
          </div>
        ) : null
      }
    >
      {state === "failed" ? (
        <p role="alert" className="rounded-md bg-brick-soft px-4 py-3 text-sm text-brick">
          {t("sat-update-failed", { version })}
        </p>
      ) : null}
      {notes ? (
        <a
          href={notes}
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-between gap-4 rounded-lg border border-rule bg-paper-raised px-4 py-3 hover:border-ink"
        >
          <span className="min-w-0">
            <span className="block text-sm text-ink">{t("sat-update-notes", { version })}</span>
            <span className="block truncate font-mono text-xs text-ink-muted">{new URL(notes).host}</span>
          </span>
          <ExternalLink className="size-4 shrink-0 text-ink-muted" aria-hidden="true" />
        </a>
      ) : (
        <p className="text-sm text-ink-muted">{t("sat-update-no-notes")}</p>
      )}
      <section aria-label={t("sat-update-steps")}>
        <p className="label-mono">{t("sat-update-steps")}</p>
        <ol className="mt-2 grid list-decimal gap-1.5 pl-5 text-sm text-ink">
          <li>{t("sat-update-step-fetch", { version, software: s.software.name })}</li>
          <li>{t("sat-update-step-restart")}</li>
          <li>{t("sat-update-step-back", { running })}</li>
        </ol>
      </section>
    </UpdateDialog>
  );
}
