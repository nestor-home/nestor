/**
 * A satellite's newer software, from its page: a button at the top says so, and opens a dialog of its
 * own (the device's mark on an ink band, never Nestor's figure) with what that version changes (the
 * notes the device found at its source, opened by the browser), what installing it does, and the
 * install itself. The dialog is the confirmation: it says everything the person is agreeing to.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleArrowUp, ExternalLink, LoaderCircle, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { api, keys, type SatelliteUpdate as Reported, type Satellite } from "@/api";
import { FormActions } from "@/components/form-actions";
import { useNotify } from "@/components/notices";
import { FormError, Notice } from "@/components/states";
import { Button } from "@/components/ui/button";
import { UpdateDialog } from "@/components/update-dialog";
import { useT } from "@/i18n";
import { useCan } from "@/lib/session";
import { DeviceMark } from "./device-mark";

type Pending = Exclude<Reported["state"], "current">;

/** The button for each state of an update, at the top of the page. */
const BUTTON: Record<Pending, { label: string; variant: "accent" | "destructive" | "outline"; Icon: LucideIcon }> = {
  available: { label: "sat-update-button", variant: "accent", Icon: CircleArrowUp },
  installing: { label: "sat-update-button-installing", variant: "outline", Icon: LoaderCircle },
  failed: { label: "sat-update-button-failed", variant: "destructive", Icon: CircleAlert },
};

/** At the top of a satellite's page, while it has a newer version, installs one or failed to. */
export function SatelliteUpdateButton({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const found = s.update;
  if (!s.can_update || !found?.version || found.state === "current") return null;
  const { label, variant, Icon } = BUTTON[found.state];
  return (
    <>
      <Button variant={variant} size="sm" onClick={() => setOpen(true)}>
        <Icon className={found.state === "installing" ? "animate-spin" : undefined} aria-hidden="true" />
        {t(label)}
      </Button>
      <SatelliteUpdate
        satellite={s}
        state={found.state}
        version={found.version}
        notes={found.notes}
        open={open}
        onOpenChange={setOpen}
      />
    </>
  );
}

function SatelliteUpdate({
  satellite: s,
  state,
  version,
  notes,
  open,
  onOpenChange,
}: {
  satellite: Satellite;
  state: Pending;
  version: string;
  notes: string | null;
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
  const running = s.software.version;
  return (
    <UpdateDialog
      open={open}
      onOpenChange={onOpenChange}
      tone="ink"
      mark={
        <span className="mb-5 grid size-20 place-items-center rounded-2xl border border-rule bg-paper-raised text-ink shadow-sm">
          <DeviceMark brand={s.brand} capabilities={s.capabilities} className="size-10" />
        </span>
      }
      title={t("sat-update-title", { name: s.name ?? s.id, version })}
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
          <FormActions hint={s.connected === false ? t("sat-update-offline") : undefined}>
            <FormError error={update.error} />
            <Button
              variant="accent"
              onClick={() => update.mutate()}
              disabled={update.isPending || s.connected === false}
            >
              {update.isPending ? "…" : t("sat-update-action", { version })}
            </Button>
          </FormActions>
        ) : null
      }
    >
      {state === "failed" ? <Notice>{t("sat-update-failed", { version })}</Notice> : null}
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
