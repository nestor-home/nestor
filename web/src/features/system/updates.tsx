/**
 * A newer Nestor: the sidebar says so, the dialog shows what changed since the running version, what
 * breaks, which satellites the new version no longer speaks to, and how to update. Nothing installs
 * from here: the household updates the way it installed Nestor, then restarts it.
 */
import { useQuery } from "@tanstack/react-query";
import { CircleArrowUp, ExternalLink } from "lucide-react";
import { useState } from "react";
import { type ChangeKind, messageOf, type Release, satellitesQuery, type Updates, updatesQuery } from "@/api";
import { CopyField } from "@/components/copy-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { Restarting, useRestart } from "@/features/config/restart";
import { useT } from "@/i18n";
import { calendarDay } from "@/lib/dates";
import { useCan } from "@/lib/session";

const KINDS: ChangeKind[] = ["breaking", "feature", "fix", "other"];

/** The commands that update an installation: the image in a container, the package otherwise. */
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
  const label = t("upd-available");
  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            tooltip={t("upd-available-version", { version: found.latest })}
            className="h-auto min-h-9 py-1.5 text-ink"
            onClick={() => setOpen(true)}
          >
            <CircleArrowUp className="size-4 shrink-0 text-ember" aria-hidden="true" />
            <span className={compact ? "sr-only" : "min-w-0 flex-1 truncate"}>{label}</span>
            {compact ? null : <span className="font-mono text-[0.75rem] text-ink-muted">{found.latest}</span>}
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
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl font-normal">
            {t("upd-title", { version: updates.latest ?? "" })}
          </DialogTitle>
          <DialogDescription>
            {t("upd-running", { version: updates.running, count: updates.releases.length })}
          </DialogDescription>
        </DialogHeader>
        {breaking ? (
          <p role="alert" className="rounded-md bg-brick-soft px-4 py-3 text-sm text-brick">
            {t("upd-breaking")}
          </p>
        ) : null}
        <Outdated ids={updates.outdated_satellites} />
        <div className="grid gap-6">
          {updates.releases.map((release) => (
            <ReleaseNotes key={release.version} release={release} />
          ))}
        </div>
        <HowTo updates={updates} />
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

function HowTo({ updates }: { updates: Updates }) {
  const t = useT();
  const canRestart = useCan("config:manage");
  const { phase, pending, error, restart } = useRestart();
  const [first, second] = commandsFor(updates);
  if (phase !== "idle") return <Restarting phase={phase} />;
  return (
    <section className="grid gap-3 border-t border-rule pt-5">
      <h3 className="font-serif text-lg font-normal">{t("upd-how")}</h3>
      <p className="text-sm text-ink-muted">{t(updates.container ? "upd-how-container" : "upd-how-package")}</p>
      <CopyField value={first} label={t("upd-command")} />
      {updates.container ? (
        <CopyField value={second} label={t("upd-command")} />
      ) : (
        <>
          <p className="text-sm text-ink-muted">{t("upd-how-pip")}</p>
          <CopyField value={second} label={t("upd-command")} />
          <p className="text-sm text-ink-muted">{t(canRestart ? "upd-then-restart" : "upd-then-ask")}</p>
          {canRestart ? (
            <div>
              <Button variant="outline" onClick={() => void restart()} disabled={pending}>
                {pending ? "…" : t("cfg-restart-now")}
              </Button>
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-brick">
              {messageOf(error)}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
