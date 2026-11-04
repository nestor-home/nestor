/**
 * A newer Nestor: the sidebar says so, the dialog shows what changed since the running version and
 * what breaks. The household updates Nestor the way it installed it.
 */
import { useQuery } from "@tanstack/react-query";
import { CircleArrowUp, ExternalLink } from "lucide-react";
import { useState } from "react";
import { type ChangeKind, type Release, updatesQuery } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { Dither } from "@/components/dither";
import { Notice } from "@/components/states";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { UpdateDialog } from "@/components/update-dialog";
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
      {
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
      }
      <NestorUpdate open={open} onOpenChange={setOpen} />
    </>
  );
}

/** What changed in each release since the running one, newest first. */
export function NestorUpdate({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const t = useT();
  const updates = useQuery(updatesQuery).data;
  const version = updates?.releases[0]?.version;
  if (!updates || !version) return null;
  return (
    <UpdateDialog
      open={open}
      onOpenChange={onOpenChange}
      tone="ember"
      mark={<AgentFigure state="laughing" size="lg" />}
      title={t("upd-title", { version })}
      description={t("upd-description")}
      running={updates.running}
      latest={version}
      aside={t("upd-behind", { count: updates.releases.length })}
      footer={<p className="text-sm text-ink-muted">{t("upd-by-hand")}</p>}
    >
      {updates.releases.some((r) => r.breaking) ? <Notice>{t("upd-breaking")}</Notice> : null}
      {updates.releases.map((release) => (
        <ReleaseNotes key={release.version} release={release} />
      ))}
    </UpdateDialog>
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
