import {
  AudioLines,
  Brain,
  Download,
  House,
  type LucideIcon,
  MessagesSquare,
  Plug,
  RadioTower,
  RotateCw,
  Server,
  Workflow,
  Wrench,
} from "lucide-react";
import { useEffect, useState } from "react";
import { type Component, type Health, type SystemInfo, systemQuery } from "@/api";
import { ConfirmFrame } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { IconTile, type TileTone } from "@/components/marks";
import { SheetPanel, SideSheet } from "@/components/overlay-form";
import { Fact, Facts, PageHeader, Section } from "@/components/page";
import { Failure, FormError, Loading } from "@/components/states";
import { Status, type StatusTone } from "@/components/status";
import { Button, buttonVariants } from "@/components/ui/button";
import { Restarting, useRestart } from "@/features/config/restart";
import { useT } from "@/i18n";
import { BrandMark, brandName, brandOf } from "@/lib/brands";
import { modelTypeLabel } from "@/lib/labels";
import { useCan, useMe } from "@/lib/session";
import { cn } from "@/lib/utils";
import { ExecutorsSection } from "./executors";
import { UpdateAvailable } from "./updates";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

/** What a group of the board holds, its mark, and the configuration page that sets it. */
interface Group {
  id: string;
  title: string;
  icon: LucideIcon;
  config?: string;
  has: (component: Component) => boolean;
}

const VOICE = new Set<Component["model_type"]>(["transcription", "speech", "speaker"]);
const slot = (name: Component["slot"]) => (c: Component) => c.slot === name;

/** The board, by what each component is, in the order a person looks for them. */
const GROUPS: Group[] = [
  {
    id: "models",
    title: "sys-slot-model",
    icon: Brain,
    config: "models",
    has: (c) => c.slot === "model" && !VOICE.has(c.model_type),
  },
  {
    id: "voice",
    title: "sys-slot-voice",
    icon: AudioLines,
    config: "models",
    has: (c) => c.slot === "model" && VOICE.has(c.model_type),
  },
  { id: "channels", title: "sys-slot-channel", icon: MessagesSquare, config: "channels", has: slot("channel") },
  { id: "home", title: "sys-slot-home", icon: House, config: "home", has: slot("home") },
  { id: "tools", title: "sys-slot-tools", icon: Wrench, config: "tools", has: slot("tools") },
  { id: "executors", title: "sys-slot-executor", icon: Workflow, config: "executors", has: slot("executor") },
  { id: "inbound", title: "sys-slot-inbound", icon: Download, config: "inbound", has: slot("inbound") },
  { id: "connectors", title: "sys-slot-connector", icon: Plug, config: "connectors", has: slot("connector") },
  { id: "satellites", title: "sys-slot-satellite", icon: RadioTower, has: slot("satellite") },
];

export const HEALTH: Record<Health, { tone: StatusTone; label: string }> = {
  started: { tone: "ok", label: "sys-health-ok" },
  degraded: { tone: "attention", label: "sys-health-degraded" },
  unavailable: { tone: "error", label: "sys-health-down" },
};
/** A component that tells nothing about itself. */
export const UNKNOWN = { tone: "idle", label: "sys-health-unknown" } as const;

const TILE: Partial<Record<Health, TileTone>> = { degraded: "amber", unavailable: "brick" };
const keyOf = (c: Component) => `${c.slot}-${c.name}`;
const unwell = (c: Component) => c.health === "unavailable" || c.health === "degraded";

/**
 * "System": what this instance is made of and how each part is doing. What is wrong comes first, with what
 * to do; then Nestor itself (its release, a restart); then every component on a board, grouped by what it is.
 * A component opens in place with all it tells about itself.
 */
export function SystemView() {
  const t = useT();
  const system = useQuery(systemQuery);
  const [open, setOpen] = useState<string | null>(null);
  const trail: Crumb[] = [{ label: t("space-settings"), link: { to: "/settings" } }, { label: t("sys-title") }];
  const components = system.data?.components ?? [];
  const wrong = components.filter(unwell);
  const opened = components.find((c) => keyOf(c) === open);
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={t("sys-title")}
        meta={
          system.data ? (
            <>
              {wrong.length ? (
                <Status tone="attention">{t("sys-unwell", { count: wrong.length })}</Status>
              ) : (
                <Status tone="ok">{t("sys-all-well")}</Status>
              )}
              <span>{t("sys-parts", { count: components.length })}</span>
            </>
          ) : undefined
        }
      />
      {system.isPending ? (
        <Loading lines={5} />
      ) : system.isError ? (
        <Failure error={system.error} retry={() => void system.refetch()} />
      ) : (
        <div className="grid gap-10">
          {wrong.length ? (
            <Section title={t("sys-attention")} count={wrong.length}>
              <Board components={wrong} urgent onOpen={setOpen} />
            </Section>
          ) : null}
          <Section title={t("sys-instance")}>
            <Instance system={system.data} />
          </Section>
          {GROUPS.map((group) => {
            const list = components.filter(group.has);
            if (!list.length) return null;
            return (
              <Section key={group.id} title={t(group.title)} count={list.length}>
                <Board components={list} onOpen={setOpen} />
              </Section>
            );
          })}
          <ExecutorsSection />
        </div>
      )}
      <SideSheet open={Boolean(opened)} onOpenChange={(next) => !next && setOpen(null)}>
        {opened ? <ComponentSheet component={opened} /> : null}
      </SideSheet>
    </>
  );
}

const groupOf = (c: Component): Group => GROUPS.find((g) => g.has(c)) ?? (GROUPS[0] as Group);

function Board({
  components,
  urgent = false,
  onOpen,
}: {
  components: Component[];
  urgent?: boolean;
  onOpen: (key: string) => void;
}) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {components.map((c) => (
        <li key={keyOf(c)}>
          <ComponentCard component={c} urgent={urgent} onOpen={() => onOpen(keyOf(c))} />
        </li>
      ))}
    </ul>
  );
}

/** The component's logo on a tile tinted by its health, or the mark of its group when it has no logo. */
function ComponentTile({ component: c }: { component: Component }) {
  const brand = brandOf(c.brand);
  const tone = (c.health && TILE[c.health]) ?? "ink";
  if (!brand) return <IconTile icon={groupOf(c).icon} tone={tone} />;
  return (
    <span
      className={cn(
        "grid size-10 shrink-0 place-items-center rounded-xl",
        tone === "brick" ? "bg-brick-soft" : tone === "amber" ? "bg-amber-soft" : "bg-paper-sunken",
      )}
    >
      <BrandMark brand={brand} className="size-5 text-ink" label={false} />
    </span>
  );
}

/** One component: what it is, how it is doing, and (when it is unwell) what to do about it. */
function ComponentCard({
  component: c,
  urgent,
  onOpen,
}: {
  component: Component;
  urgent: boolean;
  onOpen: () => void;
}) {
  const t = useT();
  const brand = brandOf(c.brand);
  const health = c.health ? HEALTH[c.health] : UNKNOWN;
  return (
    <button type="button" onClick={onOpen} className="surface flex h-full w-full flex-col gap-3 p-4 text-left">
      <span className="flex items-start justify-between gap-3">
        <ComponentTile component={c} />
        <Status tone={health.tone} className="pt-1">
          {t(health.label)}
        </Status>
      </span>
      <span className="min-w-0">
        <span className="block font-medium [overflow-wrap:anywhere] text-ink">{c.name}</span>
        <span className="block truncate text-meta text-ink-muted">
          {[c.model_type ? modelTypeLabel(c.model_type) : null, brand ? brandName(brand) : c.adapter]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </span>
      {c.fallback ? <span className="text-meta text-ink-muted">{t("sys-fallback", { model: c.fallback })}</span> : null}
      {c.health_detail ? (
        <span className={cn("text-meta", unwell(c) ? "text-ink" : "text-ink-muted")}>{c.health_detail}</span>
      ) : null}
      {urgent ? (
        <span className="mt-auto border-t border-rule pt-3 text-meta text-ink-muted">
          {t(c.health === "unavailable" ? "sys-fix-down" : "sys-fix-degraded")}
        </span>
      ) : null}
    </button>
  );
}

/** A component, opened: everything it tells about itself, and the way to its settings. */
function ComponentSheet({ component: c }: { component: Component }) {
  const t = useT();
  const canConfigure = useCan("config:manage");
  const group = groupOf(c);
  const brand = brandOf(c.brand);
  const health = c.health ? HEALTH[c.health] : UNKNOWN;
  return (
    <SheetPanel
      icon={group.icon}
      tone={(c.health && TILE[c.health]) ?? "ink"}
      kind={t(group.title)}
      title={c.name}
      description={c.health_detail ?? undefined}
      actions={
        canConfigure && group.config ? (
          <Link
            to="/config/$section"
            params={{ section: group.config }}
            className={buttonVariants({ variant: "outline" })}
          >
            {t("sys-configure")}
          </Link>
        ) : undefined
      }
    >
      {unwell(c) ? (
        <p className="text-body text-ink">{t(c.health === "unavailable" ? "sys-fix-down" : "sys-fix-degraded")}</p>
      ) : null}
      <Facts narrow>
        <Fact term={t("sys-fact-state")}>
          <Status tone={health.tone}>{t(health.label)}</Status>
        </Fact>
        {brand ? <Fact term={t("sys-fact-service")}>{brandName(brand)}</Fact> : null}
        {c.model_type ? <Fact term={t("sys-fact-type")}>{modelTypeLabel(c.model_type)}</Fact> : null}
        {c.fallback ? <Fact term={t("sys-fact-fallback")}>{c.fallback}</Fact> : null}
        <Fact term={t("sys-fact-adapter")} className="font-mono text-meta [overflow-wrap:anywhere]">
          {c.adapter}
        </Fact>
        {c.version ? (
          <Fact term={t("sys-fact-version")} className="font-mono text-meta [overflow-wrap:anywhere]">
            {c.distribution ? `${c.distribution} ${c.version}` : c.version}
          </Fact>
        ) : null}
        {c.capabilities.length ? <Fact term={t("sys-fact-can")}>{c.capabilities.join(" · ")}</Fact> : null}
        {Object.entries(c.details).map(([key, value]) => (
          <Fact key={key} term={key} className="[overflow-wrap:anywhere]">
            {value}
          </Fact>
        ))}
      </Facts>
    </SheetPanel>
  );
}

/**
 * Nestor itself: the release it runs, a newer one when there is one, what waits for a restart, and the restart,
 * which is always a person's decision.
 */
function Instance({ system }: { system: SystemInfo }) {
  const t = useT();
  const me = useMe();
  const canRestart = useCan("config:manage");
  const { phase, pending, error, clearError, restart } = useRestart();
  const [asking, setAsking] = useState(false);
  useEffect(() => {
    if (phase !== "idle") setAsking(false);
  }, [phase]);
  if (phase !== "idle") return <Restarting phase={phase} />;
  const waiting = system.pending_changes.length;
  return (
    <div className="grid gap-3">
      <div className="surface flex flex-wrap items-center gap-x-4 gap-y-4 p-5">
        <IconTile icon={Server} tone={system.restart_required ? "amber" : "ink"} size="lg" />
        <div className="min-w-0 flex-1 basis-56">
          <p className="title-card text-ink">{t("shell-version", { version: system.nestor.version })}</p>
          <p className="mt-1 text-body text-ink-muted">
            {system.restart_required
              ? t("sys-restart-waiting", { count: waiting })
              : t("sys-runs", { agent: system.agent.name })}
          </p>
        </div>
        {canRestart ? (
          <ConfirmFrame
            open={asking}
            onOpenChange={(next) => {
              if (pending) return;
              setAsking(next);
              if (!next) clearError();
            }}
            trigger={
              <Button variant="outline">
                <RotateCw aria-hidden="true" /> {t("sys-restart")}
              </Button>
            }
            title={t("sys-restart-title", { agent: me.agent.name })}
            description={t("sys-restart-text")}
            details={<FormError error={error} />}
            busy={pending}
            action={
              <Button variant="accent" onClick={() => void restart()} disabled={pending}>
                {pending ? "…" : t("sys-restart-now")}
              </Button>
            }
          />
        ) : null}
      </div>
      <UpdateAvailable compact={false} />
    </div>
  );
}
