import { useQuery } from "@tanstack/react-query";
import { type Component, type Health, systemQuery } from "@/api";
import { RowList, Section } from "@/components/page";
import { Failure, Loading } from "@/components/states";
import { Status, type StatusTone } from "@/components/status";
import { useT } from "@/i18n";
import { BrandMark, brandOf } from "@/lib/brands";
import { modelTypeLabel } from "@/lib/labels";

/** The slots the page groups components by (`ComponentOut.slot`), in this order. */
const SLOTS: Record<Component["slot"], string> = {
  model: "sys-slot-model",
  executor: "sys-slot-executor",
  channel: "sys-slot-channel",
  home: "sys-slot-home",
  tools: "sys-slot-tools",
  inbound: "sys-slot-inbound",
  connector: "sys-slot-connector",
  satellite: "sys-slot-satellite",
};

export const HEALTH: Record<Health, { tone: StatusTone; label: string }> = {
  started: { tone: "ok", label: "sys-health-ok" },
  degraded: { tone: "attention", label: "sys-health-degraded" },
  unavailable: { tone: "error", label: "sys-health-down" },
};
/** A component that tells nothing about itself. */
export const UNKNOWN = { tone: "idle", label: "sys-health-unknown" } as const;

export function SystemView() {
  const t = useT();
  const system = useQuery(systemQuery);
  if (system.isPending) return <Loading lines={5} />;
  if (system.isError) return <Failure error={system.error} retry={() => void system.refetch()} />;
  const { nestor, agent, components } = system.data;
  const unwell = components.filter((c) => c.health === "unavailable" || c.health === "degraded");
  return (
    <>
      <p className="-mt-4 mb-10 flex flex-wrap gap-x-4 gap-y-1 text-[0.85rem] text-ink-muted">
        <span>nestor {nestor.version}</span>
        <span>{agent.name}</span>
        <span className={unwell.length ? "text-amber" : "text-sage"}>
          {unwell.length ? t("sys-unwell", { count: unwell.length }) : t("sys-all-well")}
        </span>
      </p>
      {Object.entries(SLOTS).map(([slot, title]) => {
        const list = components.filter((c) => c.slot === slot);
        if (!list.length) return null;
        return (
          <Section key={slot} title={t(title)} count={list.length}>
            <RowList>
              {list.map((c) => (
                <ComponentRow key={`${c.slot}-${c.name}`} component={c} />
              ))}
            </RowList>
          </Section>
        );
      })}
    </>
  );
}

function ComponentRow({ component: c }: { component: Component }) {
  const t = useT();
  const brand = brandOf(c.brand);
  const health = c.health ? HEALTH[c.health] : UNKNOWN;
  return (
    <li className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-start gap-x-4 gap-y-1 px-5 py-3 sm:grid-cols-[1.5rem_minmax(0,1.3fr)_minmax(0,1fr)_7rem]">
      {brand ? <BrandMark brand={brand} className="mt-0.5 size-4.5 text-ink" /> : <span />}
      <div className="min-w-0">
        <p className="text-ink">
          {c.name}
          {c.model_type ? (
            <span className="ml-2 text-[0.85rem] text-ink-muted">{modelTypeLabel(c.model_type)}</span>
          ) : null}
        </p>
        <p className="truncate font-mono text-[0.7rem] text-ink-faint">{c.adapter}</p>
        {c.fallback ? (
          <p className="mt-0.5 text-xs text-ink-muted">{t("sys-fallback", { model: c.fallback })}</p>
        ) : null}
        {c.health_detail ? (
          <p className={c.health === "started" ? "mt-0.5 text-xs text-ink-muted" : "mt-0.5 text-xs text-amber"}>
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
