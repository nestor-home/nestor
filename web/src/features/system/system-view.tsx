import { useQuery } from "@tanstack/react-query";
import { type Component, type Health, type Slot, systemQuery } from "@/api";
import { Section } from "@/components/page";
import { Failure, Loading } from "@/components/states";
import { Status, type StatusTone } from "@/components/status";
import { useT } from "@/i18n";
import { BrandMark, brandOf } from "@/lib/brands";

const SLOTS: { slot: Slot; title: string; hint?: string }[] = [
  { slot: "model", title: "sys-slot-model" },
  { slot: "speech", title: "sys-slot-speech" },
  { slot: "executor", title: "sys-slot-executor" },
  { slot: "channel", title: "sys-slot-channel" },
  { slot: "presence", title: "sys-slot-presence" },
  { slot: "tools", title: "sys-slot-tools" },
  { slot: "connector", title: "sys-slot-connector" },
  { slot: "satellite", title: "sys-slot-satellite" },
  { slot: "storage", title: "sys-slot-storage" },
];

const HEALTH: Record<Health, { tone: StatusTone; label: string }> = {
  ok: { tone: "ok", label: "sys-health-ok" },
  degraded: { tone: "attention", label: "sys-health-degraded" },
  down: { tone: "error", label: "sys-health-down" },
  unknown: { tone: "idle", label: "sys-health-unknown" },
};

export function SystemView() {
  const t = useT();
  const system = useQuery(systemQuery);
  if (system.isPending) return <Loading lines={5} />;
  if (system.isError) return <Failure error={system.error} retry={() => void system.refetch()} />;
  const { nestor, agent, components } = system.data;
  const unwell = components.filter((c) => c.health === "down" || c.health === "degraded");
  return (
    <>
      <p className="-mt-4 mb-10 flex flex-wrap gap-x-4 gap-y-1 text-[0.85rem] text-ink-muted">
        <span>nestor {nestor.version}</span>
        <span>{agent.name}</span>
        <span className={unwell.length ? "text-amber" : "text-sage"}>
          {unwell.length ? t("sys-unwell", { count: unwell.length }) : t("sys-all-well")}
        </span>
      </p>
      {SLOTS.map(({ slot, title, hint }) => {
        const list = components.filter((c) => c.slot === slot);
        if (!list.length) return null;
        return (
          <Section key={slot} title={t(title)} count={list.length}>
            {hint ? <p className="-mt-1 mb-3 text-sm text-ink-muted">{t(hint)}</p> : null}
            <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
              {list.map((c) => (
                <ComponentRow key={c.id} component={c} />
              ))}
            </ul>
          </Section>
        );
      })}
    </>
  );
}

function ComponentRow({ component: c }: { component: Component }) {
  const t = useT();
  const brand = brandOf(c.brand);
  const health = HEALTH[c.health];
  return (
    <li className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-start gap-x-4 gap-y-1 px-5 py-3 sm:grid-cols-[1.5rem_minmax(0,1.3fr)_minmax(0,1fr)_7rem]">
      {brand ? <BrandMark brand={brand} className="mt-0.5 size-4.5 text-ink" /> : <span />}
      <div className="min-w-0">
        <p className="text-ink">{c.name}</p>
        <p className="truncate font-mono text-[0.7rem] text-ink-faint">{c.adapter}</p>
        {c.health_detail ? (
          <p className={c.health === "ok" ? "mt-0.5 text-xs text-ink-muted" : "mt-0.5 text-xs text-amber"}>
            {c.health_detail}
          </p>
        ) : null}
      </div>
      <p className="hidden text-[0.85rem] text-ink-muted sm:block">
        {c.version ?? "—"}
        {c.capabilities.length ? <span className="block text-ink-faint">{c.capabilities.join(" · ")}</span> : null}
      </p>
      <Status tone={health.tone} className="justify-self-end">
        {t(health.label)}
      </Status>
    </li>
  );
}
