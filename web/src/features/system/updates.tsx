/**
 * A newer Nestor: the sidebar says so, the dialog shows what changed since the running version, what
 * breaks and which satellites the new version no longer speaks to. Where Nestor runs from a Python
 * environment, the owner installs it from here and Nestor restarts on it; in a container, the dialog
 * gives the commands, since a container cannot replace its own image.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CircleArrowUp, ExternalLink } from "lucide-react";
import { useState } from "react";
import {
  api,
  type ChangeKind,
  keys,
  messageOf,
  type Release,
  satellitesQuery,
  type Updates,
  updatesQuery,
} from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { Confirm } from "@/components/confirm";
import { CopyField } from "@/components/copy-field";
import { Dither } from "@/components/dither";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { Restarting, sleep, useRestart } from "@/features/config/restart";
import { useT } from "@/i18n";
import { calendarDay } from "@/lib/dates";
import { useCan } from "@/lib/session";

const KINDS: ChangeKind[] = ["breaking", "feature", "fix", "other"];
const INSTALL_POLL_MS = 1_000;

/** The commands that update an installation by hand: the image in a container, the package otherwise. */
export function commandsFor(updates: Pick<Updates, "container">): [string, string] {
  return updates.container
    ? ["docker compose pull", "docker compose up -d"]
    : ["uv tool upgrade nestor-home", "pip install --upgrade nestor-home"];
}

/** In the sidebar's footer, only while a newer release is out. */
export function UpdateAvailable({ compact }: { compact: boolean }) {
  const t = useT();
  const canRead = useCan("system:read");
  const updates = useQuery({ ...updatesQuery, enabled: canRead });
  const [open, setOpen] = useState(false);
  const found = updates.data;
  if (!found?.releases.length || !found.latest) return null;
  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            tooltip={t("upd-available-version", { version: found.latest })}
            className="relative h-auto min-h-10 overflow-hidden bg-ember-soft/60 py-2 text-ink hover:bg-ember-soft"
            onClick={() => setOpen(true)}
          >
            <Dither shape="ramp-right" from={0} to={0.4} dot={2} className="absolute inset-0 text-ember/20" />
            <CircleArrowUp className="relative size-4 shrink-0 text-ember" aria-hidden="true" />
            <span className={compact ? "sr-only" : "relative min-w-0 flex-1 truncate"}>{t("upd-available")}</span>
            {compact ? null : <span className="relative font-mono text-[0.75rem] text-ember">{found.latest}</span>}
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
      <UpdateDialog updates={found} open={open} onOpenChange={setOpen} />
    </>
  );
}

export function UpdateDialog({
  updates,
  open,
  onOpenChange,
}: {
  updates: Updates;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
  const breaking = updates.releases.some((r) => r.breaking);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] gap-0 overflow-y-auto p-0 sm:max-w-xl">
        <header className="relative overflow-hidden px-6 pt-8 pb-6">
          <Dither shape="horizon" from={0} to={0.55} dot={3} className="absolute inset-0 text-ember/30" />
          <div className="relative flex items-end gap-5">
            <span className="-mb-2 shrink-0 max-sm:hidden">
              <AgentFigure state="laughing" size="lg" />
            </span>
            <span className="shrink-0 sm:hidden">
              <AgentFigure state="laughing" size="md" />
            </span>
            <div className="min-w-0">
              <DialogTitle className="font-serif text-2xl leading-tight font-normal text-ink">
                {t("upd-title", { version: updates.latest ?? "" })}
              </DialogTitle>
              <DialogDescription className="mt-2 flex flex-wrap items-center gap-2 font-mono text-sm text-ink-muted">
                <span>{updates.running}</span>
                <ArrowRight className="size-3.5" aria-hidden="true" />
                <span className="text-ember">{updates.latest}</span>
                <span className="font-sans">· {t("upd-behind", { count: updates.releases.length })}</span>
              </DialogDescription>
            </div>
          </div>
        </header>
        <div className="grid gap-6 px-6 pt-5 pb-6">
          {breaking ? (
            <p role="alert" className="rounded-md bg-brick-soft px-4 py-3 text-sm text-brick">
              {t("upd-breaking")}
            </p>
          ) : null}
          <Outdated ids={updates.outdated_satellites} />
          {updates.releases.map((release) => (
            <ReleaseNotes key={release.version} release={release} />
          ))}
          <Install updates={updates} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Outdated({ ids }: { ids: string[] }) {
  const t = useT();
  const canSee = useCan("satellites:read");
  const satellites = useQuery({ ...satellitesQuery, enabled: canSee && ids.length > 0 });
  if (!ids.length) return null;
  const named = new Map((satellites.data?.paired ?? []).map((s) => [s.id, s.name ?? s.id]));
  return (
    <div role="alert" className="rounded-md bg-amber-soft px-4 py-3 text-sm text-ink">
      <p>{t("upd-outdated", { count: ids.length })}</p>
      <ul className="mt-1.5 grid gap-0.5">
        {ids.map((id) => (
          <li key={id} className="[overflow-wrap:anywhere]">
            {named.get(id) ?? id}
          </li>
        ))}
      </ul>
    </div>
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

/**
 * Installs the newest release, then follows Nestor through its restart. The install runs on the
 * server, which keeps answering until it stops: `false` when it says the install failed.
 */
function useInstall(version: string) {
  const queryClient = useQueryClient();
  const restart = useRestart();
  const [installing, setInstalling] = useState(false);
  const [failed, setFailed] = useState(false);

  const installed = async (signal: AbortSignal) => {
    setInstalling(true);
    for (;;) {
      await sleep(INSTALL_POLL_MS, signal);
      const now = await api.updates().catch(() => null); // no answer: it is restarting
      if (now?.failed === version) {
        queryClient.setQueryData(keys.updates, now);
        setInstalling(false);
        setFailed(true);
        return false;
      }
      if (now === null || now.running === version) {
        setInstalling(false);
        return true;
      }
    }
  };

  /** For the confirmation: a refusal shows there; once accepted, the dialog follows the install. */
  const install = async () => {
    await api.installUpdate(version);
    setFailed(false);
    void restart.run({ ask: async () => undefined, before: installed });
  };
  return { phase: restart.phase, installing, failed, install };
}

function Install({ updates }: { updates: Updates }) {
  const t = useT();
  const canInstall = useCan("config:manage");
  const version = updates.latest ?? "";
  const { phase, installing, failed, install } = useInstall(version);
  if (phase !== "idle") return <Restarting phase={phase} />;
  if (installing || updates.installing) {
    return (
      <div role="status" className="flex items-center gap-4 rounded-lg bg-paper-sunken/70 px-5 py-4">
        <AgentFigure state="working" size="md" />
        <p className="text-sm text-ink">{t("upd-installing", { version })}</p>
      </div>
    );
  }
  const didFail = failed || updates.failed === version;
  const installable = updates.installable && canInstall;
  return (
    <section className="grid gap-3 border-t border-rule pt-5">
      {didFail ? (
        <p role="alert" className="text-sm text-brick">
          {t("upd-failed", { version, running: updates.running })}
        </p>
      ) : null}
      {installable ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Confirm
            trigger={<Button variant="accent">{t("upd-install", { version })}</Button>}
            title={t("upd-install-title", { version })}
            confirm={t("upd-install-confirm")}
            tone="accent"
            onConfirm={install}
          >
            {t("upd-install-description", { running: updates.running })}
          </Confirm>
          <p className="text-xs text-ink-muted">{t("upd-install-hint")}</p>
        </div>
      ) : (
        <ByHand updates={updates} canRestart={canInstall} />
      )}
    </section>
  );
}

/** Where Nestor cannot install itself: the commands, then the restart (a container restarts itself). */
function ByHand({ updates, canRestart }: { updates: Updates; canRestart: boolean }) {
  const t = useT();
  const [first, second] = commandsFor(updates);
  return (
    <>
      <h3 className="font-serif text-lg font-normal">{t("upd-how")}</h3>
      <p className="text-sm text-ink-muted">{t(updates.container ? "upd-how-container" : "upd-how-package")}</p>
      <CopyField value={first} label={t("upd-command")} />
      {updates.container ? null : <p className="text-sm text-ink-muted">{t("upd-how-pip")}</p>}
      <CopyField value={second} label={t("upd-command")} />
      {updates.container ? null : <Restart canRestart={canRestart} />}
    </>
  );
}

function Restart({ canRestart }: { canRestart: boolean }) {
  const t = useT();
  const { phase, pending, error, restart } = useRestart();
  if (phase !== "idle") return <Restarting phase={phase} />;
  if (!canRestart) return <p className="text-sm text-ink-muted">{t("upd-then-ask")}</p>;
  return (
    <>
      <p className="text-sm text-ink-muted">{t("upd-then-restart")}</p>
      <div>
        <Button variant="outline" onClick={() => void restart()} disabled={pending}>
          {pending ? "…" : t("cfg-restart-now")}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-brick">
          {messageOf(error)}
        </p>
      ) : null}
    </>
  );
}
