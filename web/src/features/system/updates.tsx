/**
 * A newer Nestor: the sidebar says so, the dialog shows what changed since the running version, what
 * breaks and which satellites the new version no longer speaks to. Where Nestor runs from a Python
 * environment, the owner installs it from here and Nestor restarts on it; in a container, the dialog
 * gives the commands, since a container cannot replace its own image.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleArrowUp, ExternalLink } from "lucide-react";
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
import { Notice } from "@/components/states";
import { Button } from "@/components/ui/button";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { UpdateDialog } from "@/components/update-dialog";
import { Restarting, sleep, useRestart } from "@/features/config/restart";
import { useT } from "@/i18n";
import { calendarDay } from "@/lib/dates";
import { useCan } from "@/lib/session";

const KINDS: ChangeKind[] = ["breaking", "feature", "fix", "other"];
const INSTALL_POLL_MS = 1_000;

/** The commands that update an installation by hand: the image in a container, the package otherwise. */
function commandsFor(updates: Pick<Updates, "container">): [string, string] {
  return updates.container
    ? ["docker compose pull", "docker compose up -d"]
    : ["uv tool upgrade nestor-home", "pip install --upgrade nestor-home"];
}

/** In the sidebar's footer, only while a newer release is out; its texture comes alive on hover. */
export function UpdateAvailable({ compact }: { compact: boolean }) {
  const t = useT();
  const canRead = useCan("system:read");
  const updates = useQuery({ ...updatesQuery, enabled: canRead });
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState(false);
  const found = updates.data;
  if (!found?.releases.length || !found.latest) return null;
  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            tooltip={t("upd-available-version", { version: found.latest })}
            className="group/update relative overflow-hidden"
            onClick={() => setOpen(true)}
            onPointerEnter={() => setHover(true)}
            onPointerLeave={() => setHover(false)}
          >
            <Dither
              shape="ramp-left"
              from={0}
              to={0.55}
              dot={2}
              animated={hover}
              className="absolute inset-0 text-ember/35 opacity-0 transition-opacity duration-300 group-hover/update:opacity-100"
            />
            <CircleArrowUp className="relative size-4 shrink-0 text-ember" aria-hidden="true" />
            <span className={compact ? "sr-only" : "relative min-w-0 flex-1 truncate"}>{t("upd-available")}</span>
            {compact ? null : <span className="relative font-mono text-[0.75rem] text-ink-muted">{found.latest}</span>}
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
      <NestorUpdate updates={found} open={open} onOpenChange={setOpen} />
    </>
  );
}

/** The notes, then the confirmation in their place (never on top), then the install in the notes again. */
export function NestorUpdate({
  updates,
  open,
  onOpenChange,
}: {
  updates: Updates;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
  const canInstall = useCan("config:manage");
  const version = updates.latest ?? "";
  const install = useInstall(version);
  const [confirming, setConfirming] = useState(false);
  const breaking = updates.releases.some((r) => r.breaking);
  const failed = install.failed || updates.failed === version;
  const byHand = !updates.installable || !canInstall;
  return (
    <>
      <UpdateDialog
        open={open && !confirming}
        onOpenChange={onOpenChange}
        tone="ember"
        mark={<AgentFigure state={install.installing || updates.installing ? "working" : "laughing"} size="lg" />}
        title={t("upd-title", { version })}
        description={t("upd-description")}
        running={updates.running}
        latest={version}
        aside={t("upd-behind", { count: updates.releases.length })}
        footer={
          install.phase !== "idle" ? (
            <Restarting phase={install.phase} className="bg-transparent p-0" />
          ) : install.installing || updates.installing ? (
            <p role="status" className="text-sm text-ink">
              {t("upd-installing", { version })}
            </p>
          ) : byHand ? (
            updates.container ? null : (
              <Restart canRestart={canInstall} />
            )
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <p className="text-xs text-ink-muted">{t("upd-install-hint")}</p>
              <Button variant="accent" onClick={() => setConfirming(true)}>
                {t("upd-install", { version })}
              </Button>
            </div>
          )
        }
      >
        {failed ? <Notice>{t("upd-failed", { version, running: updates.running })}</Notice> : null}
        {breaking ? <Notice>{t("upd-breaking")}</Notice> : null}
        <Outdated ids={updates.outdated_satellites} />
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
        onConfirm={install.start}
      >
        {t("upd-install-description", { running: updates.running })}
      </Confirm>
    </>
  );
}

function Outdated({ ids }: { ids: string[] }) {
  const t = useT();
  const canSee = useCan("satellites:read");
  const satellites = useQuery({ ...satellitesQuery, enabled: canSee && ids.length > 0 });
  if (!ids.length) return null;
  const named = new Map((satellites.data?.paired ?? []).map((s) => [s.id, s.name ?? s.id]));
  return (
    <Notice tone="attention">
      <p>{t("upd-outdated", { count: ids.length })}</p>
      <ul className="mt-1.5 grid gap-0.5">
        {ids.map((id) => (
          <li key={id} className="[overflow-wrap:anywhere]">
            {named.get(id) ?? id}
          </li>
        ))}
      </ul>
    </Notice>
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
  const start = async () => {
    await api.installUpdate(version);
    setFailed(false);
    void restart.run({ ask: async () => undefined, before: installed });
  };
  return { phase: restart.phase, installing, failed, start };
}

/** Where Nestor cannot install itself: the commands (the restart is in the footer; a container restarts itself). */
function ByHand({ updates }: { updates: Updates }) {
  const t = useT();
  const [first, second] = commandsFor(updates);
  return (
    <section className="grid gap-3 border-t border-rule pt-5">
      <h3 className="font-serif text-lg font-normal">{t("upd-how")}</h3>
      <p className="text-sm text-ink-muted">{t(updates.container ? "upd-how-container" : "upd-how-package")}</p>
      <CopyField value={first} label={t("upd-command")} />
      {updates.container ? null : <p className="text-sm text-ink-muted">{t("upd-how-pip")}</p>}
      <CopyField value={second} label={t("upd-command")} />
    </section>
  );
}

function Restart({ canRestart }: { canRestart: boolean }) {
  const t = useT();
  const { phase, pending, error, restart } = useRestart();
  if (phase !== "idle") return <Restarting phase={phase} className="bg-transparent p-0" />;
  if (!canRestart) return <p className="text-sm text-ink-muted">{t("upd-then-ask")}</p>;
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <p className="text-xs text-ink-muted">{error ? messageOf(error) : t("upd-then-restart")}</p>
      <Button variant="outline" onClick={() => void restart()} disabled={pending}>
        {pending ? "…" : t("cfg-restart-now")}
      </Button>
    </div>
  );
}
