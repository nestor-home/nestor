/** Spending by one dimension, every value listed whatever is kept of it, and where the figures come from. */
import { useQuery } from "@tanstack/react-query";
import type { CostBasis, UsageDimension, UsagePeriod } from "@/api";
import { usageGroupsQuery } from "@/api";
import { Section } from "@/components/page";
import { Empty } from "@/components/states";
import { Tag } from "@/components/status";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { capital } from "@/lib/utils";
import { type Ranked, RankedBars, SegmentedBar } from "./charts";
import type { Dimensions } from "./dimensions";
import { NONE, queryOf, type UsageSearch } from "./search";

type Pick = (dimension: UsageDimension, key: string | null) => void;

export const RANKINGS = [
  ["usage-who", "person"],
  ["usage-models", "consumer"],
  ["usage-what", "purpose"],
  ["usage-channels", "channel"],
] as const satisfies readonly (readonly [string, UsageDimension])[];

export function Ranking({
  title,
  dimension,
  period,
  only,
  dimensions,
  onPick,
}: {
  title: string;
  dimension: UsageDimension;
  period: UsagePeriod;
  only: UsageSearch["only"];
  dimensions: Dimensions;
  onPick: Pick;
}) {
  const t = useT();
  // every value of its own dimension stays listed, whichever is kept: one picks among them
  const groups = useQuery(usageGroupsQuery({ ...queryOf(period, only, dimension), by: dimension })).data?.groups;
  const kept = only?.[dimension] ?? [];
  const rows: Ranked[] = (groups ?? []).map((group) => ({
    key: group.key ?? null,
    label: dimensions.label(dimension, group.key ?? null, group),
    mark: dimensions.mark(dimension, group.key ?? null, group),
    cost: group.totals.cost_nusd,
    detail: t("usage-calls-count", { count: group.totals.calls }),
  }));
  return (
    <Section title={title} className="flex flex-col">
      {groups === undefined ? (
        <div className="surface h-56 animate-pulse" />
      ) : rows.length ? (
        <div className="surface flex-1 p-3">
          <RankedBars
            rows={rows}
            active={(key) => kept.includes(key ?? NONE)}
            onPick={(key) => onPick(dimension, key)}
            more={(n) => (n ? t("usage-more", { count: n }) : t("usage-less"))}
          />
        </div>
      ) : (
        <Empty>{t("usage-empty")}</Empty>
      )}
    </Section>
  );
}

const BASIS_COLOUR: Record<CostBasis, string> = {
  reported: "var(--ink-muted)",
  priced: "var(--ink-faint)",
  free: "var(--sage)",
  unknown: "var(--amber)",
};

export function Sources({ period, only, onPick }: { period: UsagePeriod; only: UsageSearch["only"]; onPick: Pick }) {
  const t = useT();
  const groups = useQuery(usageGroupsQuery({ ...queryOf(period, only, "basis"), by: "basis" })).data?.groups ?? [];
  const calls = (basis: CostBasis) => groups.find((g) => g.key === basis)?.totals.calls ?? 0;
  const unknown = calls("unknown");
  return (
    <Section title={t("usage-sources")}>
      <div className="surface grid gap-5 p-5 sm:p-6">
        <SegmentedBar
          label={t("usage-sources")}
          format={(n) => t("usage-calls-count", { count: n })}
          parts={(Object.keys(BASIS_COLOUR) as CostBasis[]).map((basis) => ({
            key: basis,
            label: capital(tr("usage-basis", { basis })),
            value: calls(basis),
            colour: BASIS_COLOUR[basis],
          }))}
        />
        {unknown ? (
          <p className="flex flex-wrap items-center gap-2 text-meta text-ink-muted">
            <Tag tone="attention">{t("usage-unknown-calls", { count: unknown })}</Tag>
            <button
              type="button"
              onClick={() => onPick("basis", "unknown")}
              className="font-medium text-ember underline-offset-4 hover:underline"
            >
              {t("usage-show-them")}
            </button>
          </p>
        ) : null}
      </div>
    </Section>
  );
}
