/**
 * "Costs": what Nestor's calls to models cost, at a glance and down to the call. One period of the household's
 * clock and one set of values kept scope every figure, chart and call below them, all in the URL; a bar, a segment or
 * a row of a ranking keeps its value, a call opens in a sheet.
 */
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { type UsageDimension, usageRhythmQuery, usageSeriesQuery, usageSummaryQuery } from "@/api";
import { Chips } from "@/components/chips";
import { PageHeader, Section } from "@/components/page";
import { Failure } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { capital, cn } from "@/lib/utils";
import { Calls } from "./calls";
import { HourByDay } from "./charts";
import { type Dimensions, useDimensions } from "./dimensions";
import { Headline } from "./headline";
import { OverTime } from "./over-time";
import { Prices } from "./prices";
import { RANKINGS, Ranking, Sources } from "./rankings";
import { PERIODS, queryOf, SPLITS, type Split, toggled, type UsageSearch } from "./search";

export function UsageView({ search, onSearch }: { search: UsageSearch; onSearch: (next: UsageSearch) => void }) {
  const t = useT();
  const period = search.period ?? "30d";
  const split: Split = search.by ?? "consumer";
  const only = search.only ?? {};
  const query = queryOf(period, only);
  const dimensions = useDimensions();
  const pick = (dimension: UsageDimension, key: string | null) =>
    onSearch({ ...search, only: toggled(only, dimension, key) });

  const summary = useQuery(usageSummaryQuery(query));
  const series = useQuery(usageSeriesQuery({ ...query, by: split }));
  const rhythm = useQuery(usageRhythmQuery(query));

  return (
    <>
      <PageHeader title={t("usage-title")} />
      <div className="grid gap-10">
        <div className="-mx-4 grid gap-3 bg-paper/90 px-4 py-3 backdrop-blur-md sm:sticky sm:top-0 sm:z-20 sm:-mx-6 sm:px-6">
          <Chips
            label={t("usage-range")}
            items={PERIODS.map((id) => ({ id, label: t(`usage-range-${id}`) }))}
            value={period}
            onChange={(next) => onSearch({ ...search, period: next })}
          />
          <Kept
            only={only}
            dimensions={dimensions}
            onPick={pick}
            onClear={() => onSearch({ ...search, only: undefined })}
          />
        </div>

        {summary.isError ? <Failure error={summary.error} retry={() => void summary.refetch()} /> : null}
        <div
          className={cn(
            "grid gap-10 transition-opacity duration-200",
            (summary.isFetching || series.isFetching) && "opacity-60",
          )}
        >
          {summary.data ? (
            <Headline
              summary={summary.data}
              trend={series.data?.points.map((p) => p.groups.reduce((s, g) => s + g.totals.cost_nusd, 0)) ?? []}
              period={period}
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
            {series.data ? (
              <OverTime series={series.data} split={split} dimensions={dimensions} onPick={(key) => pick(split, key)} />
            ) : (
              <div className="surface h-72 animate-pulse" />
            )}
          </Section>

          <div className="grid gap-10 md:grid-cols-2 2xl:grid-cols-4">
            {RANKINGS.map(([title, dimension]) => (
              <Ranking
                key={dimension}
                title={t(title)}
                dimension={dimension}
                period={period}
                only={only}
                dimensions={dimensions}
                onPick={pick}
              />
            ))}
          </div>

          <div className="grid gap-10 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
            <Section title={t("usage-when")}>
              <div className="surface p-5 sm:p-6">
                <HourByDay beats={rhythm.data?.beats ?? []} label={t("usage-when")} />
              </div>
            </Section>
            <Sources period={period} only={only} onPick={pick} />
          </div>

          <Prices period={period} only={only} />
          <Calls query={query} dimensions={dimensions} />
        </div>
      </div>
    </>
  );
}

/** The values kept, as chips that let go of themselves, as the journal shows its filters. */
function Kept({
  only,
  dimensions,
  onPick,
  onClear,
}: {
  only: UsageSearch["only"];
  dimensions: Dimensions;
  onPick: (dimension: UsageDimension, key: string | null) => void;
  onClear: () => void;
}) {
  const t = useT();
  const kept = Object.entries(only ?? {}).flatMap(([dimension, values]) =>
    (values ?? []).map((value) => ({ dimension: dimension as UsageDimension, key: value || null })),
  );
  if (!kept.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {kept.map(({ dimension, key }) => {
        const value = dimensions.label(dimension, key);
        return (
          <Button
            key={`${dimension}:${key}`}
            variant="pill"
            size="sm"
            className="max-w-full border-ink"
            onClick={() => onPick(dimension, key)}
            aria-label={t("usage-filter-remove", { value })}
          >
            <span className="text-ink-muted">{capital(tr("usage-dimension", { dimension }))}</span>
            {value}
            <X className="text-ink-faint" aria-hidden="true" />
          </Button>
        );
      })}
      <Button variant="ghost" size="sm" onClick={onClear}>
        {t("usage-filter-clear")}
      </Button>
    </div>
  );
}
