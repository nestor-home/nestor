/**
 * "Costs": what Nestor's calls to models cost, at a glance and down to the call. One period and one set of values
 * kept scope every figure, chart and call below them, all in the URL; a bar, a segment or a row of a ranking keeps
 * its value, a call opens in a sheet.
 */
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, X } from "lucide-react";
import { useState } from "react";
import {
  type UsageCall,
  type UsageDimension,
  type UsageGroup,
  type UsageTotals,
  usageCallsQuery,
  usageGroupsQuery,
  usagePricesQuery,
  usageSeriesQuery,
  usageSummaryQuery,
} from "@/api";
import { Chips } from "@/components/chips";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure } from "@/components/states";
import { Tag } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/use-now";
import { activeLocale, useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { cn } from "@/lib/utils";
import { CallSheet } from "./call-sheet";
import {
  HourByDay,
  OTHER_KEY,
  type Ranked,
  RankedBars,
  SegmentedBar,
  type Series,
  Sparkline,
  StackedColumns,
} from "./charts";
import { capital, type Dimensions, OTHER, useDimensions } from "./dimensions";
import { count, money, share } from "./format";
import { Prices } from "./prices";
import {
  filtersOf,
  type Period,
  periodOf,
  RANGES,
  type Range,
  SPLITS,
  type Split,
  toggled,
  type UsageSearch,
} from "./search";

const SERIES = 6;

export function UsageView({ search, onSearch }: { search: UsageSearch; onSearch: (next: UsageSearch) => void }) {
  const t = useT();
  const now = useNow(60_000);
  const range: Range = search.range ?? "30d";
  const split: Split = search.by ?? "consumer";
  const only = search.only ?? {};
  const period = periodOf(range, now);
  const filters = filtersOf(period, only);
  const dimensions = useDimensions(period, split);
  const pick = (dimension: UsageDimension, key: string | null) =>
    onSearch({ ...search, only: toggled(only, dimension, key) });

  const summary = useQuery(usageSummaryQuery(filters));
  const series = useQuery(usageSeriesQuery({ ...filters, every: period.every, by: split }));
  const hours = useQuery(usageSeriesQuery({ ...filters, every: "hour" }));

  const active = Object.entries(only).flatMap(([dimension, values]) =>
    (values ?? []).map((value) => ({ dimension: dimension as UsageDimension, value })),
  );
  const loading = summary.isFetching || series.isFetching;

  return (
    <>
      <PageHeader title={t("usage-title")} />
      <div className="grid gap-10">
        <div className="-mx-4 grid gap-3 bg-paper/90 px-4 py-3 backdrop-blur-md sm:sticky sm:top-0 sm:z-20 sm:-mx-6 sm:px-6">
          <Chips
            label={t("usage-range")}
            items={RANGES.map((id) => ({ id, label: t(`usage-range-${id}`) }))}
            value={range}
            onChange={(next) => onSearch({ ...search, range: next })}
          />
          {active.length ? (
            <div className="flex flex-wrap items-center gap-2">
              {active.map(({ dimension, value }) => (
                <button
                  key={`${dimension}:${value}`}
                  type="button"
                  onClick={() => pick(dimension, value || null)}
                  className="inline-flex h-8 items-center gap-2 rounded-full bg-ink py-0 pr-2.5 pl-3 text-meta text-paper"
                >
                  <span className="text-paper/65">{capital(tr("usage-dimension", { dimension }))}</span>
                  <span className="font-medium">{dimensions.label(dimension, value || null)}</span>
                  <X aria-hidden="true" className="size-3.5" />
                  <span className="sr-only">{t("usage-filter-remove")}</span>
                </button>
              ))}
              <Button variant="ghost" size="sm" onClick={() => onSearch({ ...search, only: undefined })}>
                {t("usage-filter-clear")}
              </Button>
            </div>
          ) : null}
        </div>

        {summary.isError ? <Failure error={summary.error} retry={() => void summary.refetch()} /> : null}
        <div className={cn("grid gap-10 transition-opacity duration-200", loading && "opacity-60")}>
          {summary.data ? (
            <Headline
              totals={summary.data.totals}
              previous={summary.data.previous}
              month={summary.data.month}
              projected={summary.data.projected_month_nusd}
              conversations={summary.data.conversations}
              daily={series.data?.points.map((p) => p.groups.reduce((s, g) => s + g.totals.cost_nusd, 0)) ?? []}
              range={range}
            />
          ) : (
            <div className="surface h-48 animate-pulse" />
          )}

          <Section
            title={t("usage-over-time")}
            aside={
              <Chips
                label={t("usage-split")}
                items={SPLITS.map((id) => ({ id, label: capital(tr("usage-dimension", { dimension: id })) }))}
                value={split}
                onChange={(by) => onSearch({ ...search, by })}
              />
            }
          >
            <OverTime
              points={series.data?.points ?? []}
              split={split}
              period={period}
              dimensions={dimensions}
              onPick={(key) => pick(split, key)}
            />
          </Section>

          <div className="grid gap-10 md:grid-cols-2 2xl:grid-cols-4">
            <Ranking
              title={t("usage-who")}
              dimension="person"
              period={period}
              only={only}
              dimensions={dimensions}
              onPick={pick}
            />
            <Ranking
              title={t("usage-models")}
              dimension="consumer"
              period={period}
              only={only}
              dimensions={dimensions}
              onPick={pick}
            />
            <Ranking
              title={t("usage-what")}
              dimension="purpose"
              period={period}
              only={only}
              dimensions={dimensions}
              onPick={pick}
            />
            <Ranking
              title={t("usage-channels")}
              dimension="channel"
              period={period}
              only={only}
              dimensions={dimensions}
              onPick={pick}
            />
          </div>

          <div className="grid gap-10 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
            <Section title={t("usage-when")}>
              <div className="surface p-5 sm:p-6">
                <HourByDay points={hours.data?.points ?? []} label={t("usage-when")} />
              </div>
            </Section>
            <Sources period={period} only={only} onPick={pick} />
          </div>

          <Prices period={period} only={only} />

          <Calls filters={filters} dimensions={dimensions} />
        </div>
      </div>
    </>
  );
}

// -- the period at a glance ---------------------------------------------------------------------------

function Headline({
  totals,
  previous,
  month,
  projected,
  conversations,
  daily,
  range,
}: {
  totals: UsageTotals;
  previous: UsageTotals;
  month: UsageTotals;
  projected: number;
  conversations: number;
  daily: number[];
  range: Range;
}) {
  const t = useT();
  const change = previous.cost_nusd > 0 ? totals.cost_nusd / previous.cost_nusd - 1 : null;
  const input = totals.units.input_tokens ?? 0;
  const cached = totals.units.cached_input_tokens ?? 0;
  const Arrow = change !== null && change < 0 ? ArrowDownRight : ArrowUpRight;
  return (
    <section
      aria-label={t("usage-glance")}
      className="surface grid overflow-hidden lg:grid-cols-[minmax(0,1.25fr)_minmax(0,2fr)]"
    >
      <div className="relative grid content-between gap-6 p-6 sm:p-7">
        <div>
          <p className="caption">{t(`usage-spent-${range}`)}</p>
          <p className="mt-2 font-sans text-[clamp(2.75rem,6vw,3.75rem)] leading-none font-semibold tracking-[-0.03em] text-ink">
            {money(totals.cost_nusd)}
          </p>
          <p className="mt-3 flex items-center gap-1.5 text-meta text-ink-muted">
            {change === null ? (
              t("usage-no-before")
            ) : (
              <>
                <Arrow aria-hidden="true" className={cn("size-4", change > 0 ? "text-brick" : "text-sage")} />
                <span className="font-medium text-ink tabular">
                  {new Intl.NumberFormat(activeLocale(), {
                    style: "percent",
                    maximumFractionDigits: 0,
                    signDisplay: "exceptZero",
                  }).format(change)}
                </span>
                {t("usage-vs-before", { spent: money(previous.cost_nusd) })}
              </>
            )}
          </p>
        </div>
        <Sparkline values={daily} className="-mx-1" />
      </div>
      <div className="grid grid-cols-2 border-t border-rule lg:border-t-0 lg:border-l">
        <Stat
          term={t("usage-month-end")}
          value={money(projected)}
          detail={t("usage-month-so-far", { spent: money(month.cost_nusd) })}
        />
        <Stat
          term={t("usage-per-conversation")}
          value={conversations ? money(Math.round(totals.cost_nusd / conversations)) : "-"}
          detail={t("usage-conversations", { count: conversations })}
          className="border-l border-rule"
        />
        <Stat
          term={t("usage-calls")}
          value={count(totals.calls)}
          detail={totals.unknown ? t("usage-unknown-calls", { count: totals.unknown }) : t("usage-all-known")}
          tone={totals.unknown ? "attention" : undefined}
          className="border-t border-rule"
        />
        <Stat
          term={t("usage-cache")}
          value={input ? share(cached, input) : "-"}
          detail={t("usage-input-tokens", { tokens: count(input) })}
          className="border-t border-l border-rule"
        />
      </div>
    </section>
  );
}

function Stat({
  term,
  value,
  detail,
  tone,
  className,
}: {
  term: string;
  value: string;
  detail: string;
  tone?: "attention";
  className?: string;
}) {
  return (
    <div className={cn("grid content-start gap-1 p-5 sm:p-6", className)}>
      <p className="caption">{term}</p>
      <p className="text-[1.65rem] leading-tight font-semibold tracking-[-0.02em] text-ink">{value}</p>
      <p className={cn("text-meta", tone === "attention" ? "text-amber" : "text-ink-muted")}>{detail}</p>
    </div>
  );
}

// -- over time -------------------------------------------------------------------------------------------

function OverTime({
  points,
  split,
  period,
  dimensions,
  onPick,
}: {
  points: { start: string; groups: UsageGroup[] }[];
  split: Split;
  period: Period;
  dimensions: Dimensions;
  onPick: (key: string | null) => void;
}) {
  const t = useT();
  const spent = new Map<string, { cost: number; group: UsageGroup }>();
  for (const point of points)
    for (const group of point.groups) {
      const key = group.key ?? "";
      const known = spent.get(key);
      spent.set(key, { cost: (known?.cost ?? 0) + group.totals.cost_nusd, group: known?.group ?? group });
    }
  const ranked = [...spent.entries()].sort((a, b) => b[1].cost - a[1].cost);
  // the costliest that have a colour of their own; the rest share one
  const coloured = ranked.filter(([key]) => dimensions.colour(split, key || null) !== OTHER).slice(0, SERIES);
  const kept = new Set(coloured.map(([key]) => key));
  const rest = ranked.filter(([key]) => !kept.has(key));
  const series: Series[] = [
    ...coloured.map(([key, { group }]) => ({
      key,
      label: dimensions.label(split, key || null, group),
      colour: dimensions.colour(split, key || null),
    })),
    ...(rest.length ? [{ key: OTHER_KEY, label: t("usage-other", { count: rest.length }), colour: OTHER }] : []),
  ];
  if (!points.length) return <Empty>{t("usage-empty")}</Empty>;
  return (
    <div className="surface grid gap-5 p-5 sm:p-6">
      <ul className="flex flex-wrap gap-x-5 gap-y-2">
        {series.map((s) => {
          const cost =
            s.key === OTHER_KEY ? rest.reduce((sum, [, r]) => sum + r.cost, 0) : (spent.get(s.key)?.cost ?? 0);
          return (
            <li key={s.key}>
              <button
                type="button"
                disabled={s.key === OTHER_KEY}
                onClick={() => onPick(s.key || null)}
                className="flex items-center gap-2 rounded-md text-meta enabled:hover:text-ink"
              >
                <span aria-hidden="true" className="size-2.5 rounded-[3px]" style={{ background: s.colour }} />
                <span className="text-ink-muted">{s.label}</span>
                <span className="font-medium text-ink tabular">{money(cost)}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <StackedColumns
        points={points}
        series={series}
        keyOf={(group) => (kept.has(group.key ?? "") ? (group.key ?? "") : OTHER_KEY)}
        every={period.every}
        since={period.since}
        until={period.every === "hour" ? new Date(period.since.getTime() + 86_400_000) : period.until}
        label={t("usage-over-time")}
        onPick={(key) => key !== OTHER_KEY && onPick(key || null)}
      />
    </div>
  );
}

// -- rankings ------------------------------------------------------------------------------------------

function Ranking({
  title,
  dimension,
  period,
  only,
  dimensions,
  onPick,
}: {
  title: string;
  dimension: UsageDimension;
  period: Period;
  only: UsageSearch["only"];
  dimensions: Dimensions;
  onPick: (dimension: UsageDimension, key: string | null) => void;
}) {
  const t = useT();
  // every value of its own dimension stays listed, whichever is kept: one picks among them
  const groups = useQuery(usageGroupsQuery({ ...filtersOf(period, only, dimension), by: dimension })).data?.groups;
  const kept = only?.[dimension] ?? [];
  const rows: Ranked[] = (groups ?? []).map((group) => ({
    key: group.key ?? null,
    label: dimensions.label(dimension, group.key ?? null, group),
    mark: dimensions.mark(dimension, group.key ?? null, group),
    cost: group.totals.cost_nusd,
    calls: group.totals.calls,
    detail: t("usage-calls-count", { count: group.totals.calls }),
  }));
  const total = rows.reduce((sum, r) => sum + r.cost, 0);
  return (
    <Section title={title} className="flex flex-col">
      {groups === undefined ? (
        <div className="surface h-56 animate-pulse" />
      ) : rows.length ? (
        <div className="surface flex-1 p-3">
          <RankedBars
            rows={rows}
            total={total}
            active={(key) => kept.includes(key ?? "")}
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

// -- where the figures come from ---------------------------------------------------------------------------

const BASIS_COLOUR = {
  reported: "var(--ink-muted)",
  priced: "var(--ink-faint)",
  free: "var(--sage)",
  unknown: "var(--amber)",
} as const;

function Sources({
  period,
  only,
  onPick,
}: {
  period: Period;
  only: UsageSearch["only"];
  onPick: (dimension: UsageDimension, key: string | null) => void;
}) {
  const t = useT();
  const groups = useQuery(usageGroupsQuery({ ...filtersOf(period, only, "basis"), by: "basis" })).data?.groups ?? [];
  const calls = (basis: keyof typeof BASIS_COLOUR) => groups.find((g) => g.key === basis)?.totals.calls ?? 0;
  const unknown = calls("unknown");
  return (
    <Section title={t("usage-sources")}>
      <div className="surface grid gap-5 p-5 sm:p-6">
        <SegmentedBar
          label={t("usage-sources")}
          format={(n) => t("usage-calls-count", { count: n })}
          parts={(["reported", "priced", "free", "unknown"] as const).map((basis) => ({
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

// -- every call ---------------------------------------------------------------------------------------------

function Calls({ filters, dimensions }: { filters: ReturnType<typeof filtersOf>; dimensions: Dimensions }) {
  const t = useT();
  const calls = useInfiniteQuery(usageCallsQuery(filters));
  const prices = useQuery(usagePricesQuery).data;
  const [open, setOpen] = useState<UsageCall | null>(null);
  const [shown, setShown] = useState(false);
  const rows = calls.data?.pages.flatMap((p) => p.calls) ?? [];
  const at = (iso: string) =>
    new Intl.DateTimeFormat(activeLocale(), {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  return (
    <Section title={t("usage-calls-title")}>
      {calls.isError ? <Failure error={calls.error} retry={() => void calls.refetch()} /> : null}
      {rows.length ? (
        <div className="surface overflow-hidden">
          <ul className="divide-y divide-rule">
            {rows.map((call) => {
              const model = prices?.prices.find((p) => p.consumer === call.consumer);
              return (
                <li key={call.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(call);
                      setShown(true);
                    }}
                    className="grid w-full grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 px-4 py-3 text-left transition-colors hover:bg-paper-sunken/60 sm:grid-cols-[1.5rem_minmax(0,1.3fr)_minmax(0,1fr)_7rem_6.5rem] sm:px-5"
                  >
                    <span className="grid size-6 place-items-center">{dimensions.mark("consumer", call.consumer)}</span>
                    <span className="min-w-0">
                      <span className="block truncate text-body font-medium text-ink">
                        {capital(tr("usage-purpose", { purpose: call.purpose }))}
                        {call.outcome !== "ok" ? (
                          <span className="ml-2 text-meta font-normal text-amber">
                            {tr("usage-outcome", { outcome: call.outcome })}
                          </span>
                        ) : null}
                      </span>
                      <span className="block truncate text-meta text-ink-muted">
                        {call.consumer}
                        {(call.served ?? model?.model) ? ` · ${call.served ?? model?.model}` : ""}
                      </span>
                    </span>
                    <span className="hidden min-w-0 items-center gap-2 truncate text-meta text-ink-muted sm:flex">
                      {dimensions.mark("person", call.person?.id ?? null)}
                      <span className="truncate">{dimensions.label("person", call.person?.id ?? null)}</span>
                    </span>
                    <span className="hidden text-meta text-ink-faint tabular sm:block">{at(call.at)}</span>
                    <span className="text-right text-body font-semibold text-ink tabular">
                      {call.cost_nusd === null || call.cost_nusd === undefined ? (
                        <Tag tone="attention">{tr("usage-basis", { basis: "unknown" })}</Tag>
                      ) : (
                        money(call.cost_nusd)
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          {calls.hasNextPage ? (
            <div className="border-t border-rule p-3 text-center">
              <Button variant="ghost" onClick={() => void calls.fetchNextPage()} disabled={calls.isFetchingNextPage}>
                {t("usage-calls-more")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : calls.isPending ? (
        <div className="surface h-64 animate-pulse" />
      ) : (
        <Empty>{t("usage-empty")}</Empty>
      )}
      <CallSheet
        call={open}
        open={shown}
        onOpenChange={setShown}
        onClosed={() => setOpen(null)}
        dimensions={dimensions}
      />
    </Section>
  );
}
