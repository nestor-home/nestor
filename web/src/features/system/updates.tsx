/**
 * A newer Nestor: the sidebar says so, the dialog shows what changed since the running version, what
 * breaks and which satellites the new version no longer speaks to. Where Nestor runs from a Python
 * environment, the owner installs it from here and Nestor restarts on it; otherwise the dialog gives
 * the commands the server names for the way Nestor is installed.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleArrowUp, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type ChangeKind, keys, type Release, type Updates, updatesQuery } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { Confirm } from "@/components/confirm";
import { CopyField } from "@/components/copy-field";
import { Dither } from "@/components/dither";
import { FormActions } from "@/components/form-actions";
import { FormError, Notice } from "@/components/states";
import { Button } from "@/components/ui/button";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { UpdateDialog } from "@/components/update-dialog";
import { Restarting, useRestart } from "@/features/config/restart";
import { useT } from "@/i18n";
import { calendarDay } from "@/lib/dates";
import { useCan } from "@/lib/session";

const KINDS: ChangeKind[] = ["breaking", "feature", "fix", "other"];

/** In the sidebar's footer, only while a newer release is out; its texture comes alive on hover. */
export function UpdateAvailable({ compact }: { compact: boolean }) {
  const t = useT();
  const canRead = useCan("system:read");
  const updates = useQuery({ ...updatesQuery, enabled: canRead });
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState(false);
  const latest = updates.data?.releases[0]?.version;
  if (!latest) return null;
  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            tooltip={t("upd-available-version", { version: latest })}
            className="relative overflow-hidden"
            onClick={() => setOpen(true)}
            onPointerEnter={() => setHover(true)}
            onPointerLeave={() => setHover(false)}
          >
            {hover ? (
              <Dither
                shape="ramp-left"
                from={0}
                to={0.55}
                dot={2}
                animated
                className="absolute inset-0 text-ember/35"
              />
            ) : null}
            <CircleArrowUp className="relative size-4 shrink-0 text-ember" aria-hidden="true" />
            <span className={compact ? "sr-only" : "relative min-w-0 flex-1 truncate"}>{t("upd-available")}</span>
            {compact ? null : <span className="relative font-mono text-[0.75rem] text-ink-muted">{latest}</span>}
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
      <NestorUpdate open={open} onOpenChange={setOpen} />
    </>
  );
}

/**
 * The notes, then the confirmation in their place (never on top), then the install in the notes again.
 * What the install is doing comes from the server alone (`installing`, `failed`); once it stops
 * answering, or answers on the new version, the dialog follows Nestor through its restart.
 */
export function NestorUpdate({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const canInstall = useCan("config:manage");
  const queryClient = useQueryClient();
  const query = useQuery(updatesQuery);
  const { phase, waitBack } = useRestart();
  const [confirming, setConfirming] = useState(false);
  const [following, setFollowing] = useState(false);
  const updates = query.data;
  const version = updates?.releases[0]?.version ?? "";
  const gone = query.isError || updates?.running === version;

  useEffect(() => {
    if (following && gone && phase === "idle") {
      setFollowing(false);
      void waitBack();
    }
  }, [following, gone, phase, waitBack]);

  if (!updates || !version) return null;
  const install = async () => {
    queryClient.setQueryData(keys.updates, await api.installUpdate(version));
    setFollowing(true);
  };
  const byHand = !updates.installable || !canInstall;
  return (
    <>
      <UpdateDialog
        open={open && !confirming}
        onOpenChange={onOpenChange}
        tone="ember"
        mark={<AgentFigure state={updates.installing ? "working" : "laughing"} size="lg" />}
        title={t("upd-title", { version })}
        description={t("upd-description")}
        running={updates.running}
        latest={version}
        aside={t("upd-behind", { count: updates.releases.length })}
        footer={
          phase !== "idle" ? (
            <Restarting phase={phase} className="bg-transparent p-0" />
          ) : updates.installing ? (
            <p role="status" className="text-sm text-ink">
              {t("upd-installing", { version })}
            </p>
          ) : !byHand ? (
            <FormActions hint={t("upd-install-hint")}>
              <Button variant="accent" onClick={() => setConfirming(true)}>
                {t("upd-install", { version })}
              </Button>
            </FormActions>
          ) : updates.installation !== "container" ? (
            <Restart canRestart={canInstall} />
          ) : null
        }
      >
        {updates.failed === version ? <Notice>{t("upd-failed", { version, running: updates.running })}</Notice> : null}
        {updates.releases.some((r) => r.breaking) ? <Notice>{t("upd-breaking")}</Notice> : null}
        {updates.left_behind.length ? (
          <Notice tone="attention">
            <p>{t("upd-outdated", { count: updates.left_behind.length })}</p>
            <ul className="mt-1.5 grid gap-0.5">
              {updates.left_behind.map((s) => (
                <li key={s.id} className="[overflow-wrap:anywhere]">
                  {s.name ?? s.id}
                </li>
              ))}
            </ul>
          </Notice>
        ) : null}
        {updates.releases.map((release) => (
          <ReleaseNotes key={release.version} release={release} />
        ))}
        {byHand ? <ByHand updates={updates} /> : null}
      </UpdateDialog>
      <Confirm
        open={open && confirming}
        onOpenChange={(next) => {
          if (!next) setConfirming(false);
        }}
        title={t("upd-install-title", { version })}
        confirm={t("upd-install-confirm")}
        tone="accent"
        onConfirm={install}
      >
        {t("upd-install-description", { running: updates.running })}
      </Confirm>
    </>
  );
}

function ReleaseNotes({ release }: { release: Release }) {
  const t = useT();
  return (
    <section aria-label={t("upd-release", { version: release.version })}>
      <h3 className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-sm text-ink">{release.version}</span>
        <span className="text-xs text-ink-muted">{calendarDay(release.date)}</span>
        <a
          href={release.url}
          target="_blank"
          rel="noreferrer"
          className="ml-auto inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink"
        >
          {t("upd-notes")}
          <ExternalLink className="size-3" aria-hidden="true" />
        </a>
      </h3>
      {KINDS.map((kind) => {
        const changes = release.changes.filter((c) => c.kind === kind);
        if (!changes.length) return null;
        return (
          <div key={kind} className="mt-3">
            <p className={kind === "breaking" ? "label-mono text-brick" : "label-mono"}>{t(`upd-kind-${kind}`)}</p>
            <ul className="mt-1 grid list-disc gap-1 pl-5 text-sm text-ink" lang="en">
              {changes.map((c) => (
                <li key={c.text} className="[overflow-wrap:anywhere]">
                  {c.text}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}

/** Where Nestor does not install itself: the commands the server names for how it is installed. */
function ByHand({ updates }: { updates: Updates }) {
  const t = useT();
  return (
    <section className="grid gap-3 border-t border-rule pt-5">
      <h3 className="font-serif text-lg font-normal">{t("upd-how")}</h3>
      <p className="text-sm text-ink-muted">{t(`upd-how-${updates.installation ?? "editable"}`)}</p>
      {updates.commands.map((command) => (
        <CopyField key={command} value={command} label={t("upd-command")} />
      ))}
    </section>
  );
}

function Restart({ canRestart }: { canRestart: boolean }) {
  const t = useT();
  const { phase, pending, error, restart } = useRestart();
  if (phase !== "idle") return <Restarting phase={phase} className="bg-transparent p-0" />;
  if (!canRestart) return <p className="text-sm text-ink-muted">{t("upd-then-ask")}</p>;
  return (
    <FormActions hint={t("upd-then-restart")}>
      <FormError error={error} />
      <Button variant="outline" onClick={() => void restart()} disabled={pending}>
        {pending ? "…" : t("cfg-restart-now")}
      </Button>
    </FormActions>
  );
}
