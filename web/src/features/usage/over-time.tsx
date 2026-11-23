/** Spending over the period, split by one dimension: its legend, then its stacked columns. */
import { useMemo } from "react";
import type { UsageGroup, UsageSeries } from "@/api";
import { Empty } from "@/components/states";
import { useT } from "@/i18n";
import { OTHER_KEY, type Series, StackedColumns } from "./charts";
import { type Dimensions, OTHER, SERIES } from "./dimensions";
import { money } from "./format";
import { NONE, type Split } from "./search";

export function OverTime({
  series,
  split,
  dimensions,
  onPick,
}: {
  series: UsageSeries;
  split: Split;
  dimensions: Dimensions;
  onPick: (key: string | null) => void;
}) {
  const t = useT();
  // what the period spent on each value, the costliest first: it orders the colours of values without an order
  const spent = useMemo(() => {
    const sums = new Map<string, { cost: number; group: UsageGroup }>();
    for (const point of series.points)
      for (const group of point.groups) {
        const key = group.key ?? NONE;
        const known = sums.get(key);
        sums.set(key, { cost: (known?.cost ?? 0) + group.totals.cost_nusd, group: known?.group ?? group });
      }
    return [...sums.entries()].sort((a, b) => b[1].cost - a[1].cost);
  }, [series]);
  const ranked = spent.map(([key]) => key || null);
  const colourOf = (key: string) => dimensions.colour(split, key || null, ranked);
  const coloured = spent.filter(([key]) => colourOf(key) !== OTHER).slice(0, SERIES);
  const kept = new Set(coloured.map(([key]) => key));
  const rest = spent.filter(([key]) => !kept.has(key));
  const legend: (Series & { cost: number })[] = [
    ...coloured.map(([key, { cost, group }]) => ({
      key,
      cost,
      label: dimensions.label(split, key || null, group),
      colour: colourOf(key),
    })),
    ...(rest.length
      ? [
          {
            key: OTHER_KEY,
            cost: rest.reduce((sum, [, r]) => sum + r.cost, 0),
            label: t("usage-other", { count: rest.length }),
            colour: OTHER,
          },
        ]
      : []),
  ];
  // stable while the coloured values are, so that the columns are not stacked again on every move of the pointer
  const coloredKeys = coloured.map(([key]) => key).join("\n");
  const keyOf = useMemo(() => {
    const own = new Set(coloredKeys.split("\n"));
    return (group: UsageGroup) => (own.has(group.key ?? NONE) ? (group.key ?? NONE) : OTHER_KEY);
  }, [coloredKeys]);
  if (!series.points.length) return <Empty>{t("usage-empty")}</Empty>;
  const pick = (key: string) => key !== OTHER_KEY && onPick(key || null);
  return (
    <div className="surface grid gap-5 p-5 sm:p-6">
      <ul className="flex flex-wrap gap-x-5 gap-y-2">
        {legend.map((s) => (
          <li key={s.key}>
            <button
              type="button"
              disabled={s.key === OTHER_KEY}
              onClick={() => pick(s.key)}
              className="flex items-center gap-2 rounded-md text-meta enabled:hover:text-ink"
            >
              <span aria-hidden="true" className="size-2.5 rounded-[3px]" style={{ background: s.colour }} />
              <span className="text-ink-muted">{s.label}</span>
              <span className="font-medium text-ink tabular">{money(s.cost)}</span>
            </button>
          </li>
        ))}
      </ul>
      <StackedColumns
        points={series.points}
        series={legend}
        keyOf={keyOf}
        span={series.span}
        label={t("usage-over-time")}
        onPick={pick}
      />
    </div>
  );
}
