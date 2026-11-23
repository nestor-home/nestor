/** The period at a glance: what was spent, against the period before, where the month is heading, and how. */
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { UsagePeriod, UsageSummary } from "@/api";
import { activeLocale, useT } from "@/i18n";
import { cn } from "@/lib/utils";
import { Sparkline } from "./charts";
import { count, money, share } from "./format";

export function Headline({ summary, trend, period }: { summary: UsageSummary; trend: number[]; period: UsagePeriod }) {
  const t = useT();
  const { totals, previous, month } = summary;
  const change = previous.cost_nusd > 0 ? totals.cost_nusd / previous.cost_nusd - 1 : null;
  const input = totals.units.input_tokens ?? 0;
  const Arrow = change !== null && change < 0 ? ArrowDownRight : ArrowUpRight;
  const signed = new Intl.NumberFormat(activeLocale(), {
    style: "percent",
    maximumFractionDigits: 0,
    signDisplay: "exceptZero",
  });
  return (
    <section
      aria-label={t("usage-glance")}
      className="surface grid overflow-hidden lg:grid-cols-[minmax(0,1.25fr)_minmax(0,2fr)]"
    >
      <div className="grid content-between gap-6 p-6 sm:p-7">
        <div>
          <p className="caption">{t(`usage-spent-${period}`)}</p>
          <p className="mt-2 font-sans text-[clamp(2.75rem,6vw,3.75rem)] leading-none font-semibold tracking-[-0.03em] text-ink">
            {money(totals.cost_nusd)}
          </p>
          <p className="mt-3 flex items-center gap-1.5 text-meta text-ink-muted">
            {change === null ? (
              t("usage-no-before")
            ) : (
              <>
                <Arrow aria-hidden="true" className={cn("size-4", change > 0 ? "text-brick" : "text-sage")} />
                <span className="font-medium text-ink tabular">{signed.format(change)}</span>
                {t("usage-vs-before", { spent: money(previous.cost_nusd) })}
              </>
            )}
          </p>
        </div>
        <Sparkline values={trend} className="-mx-1" />
      </div>
      <div className="grid grid-cols-2 border-t border-rule lg:border-t-0 lg:border-l">
        <Stat
          term={t("usage-month-end")}
          value={money(summary.projected_month_nusd)}
          detail={t("usage-month-so-far", { spent: money(month.cost_nusd) })}
        />
        <Stat
          term={t("usage-per-conversation")}
          value={totals.conversations ? money(Math.round(totals.conversed_nusd / totals.conversations)) : "-"}
          detail={t("usage-conversations", { count: totals.conversations })}
          className="border-l border-rule"
        />
        <Stat
          term={t("usage-calls")}
          value={count(totals.calls)}
          detail={totals.unknown ? t("usage-unknown-calls", { count: totals.unknown }) : t("usage-all-known")}
          attention={totals.unknown > 0}
          className="border-t border-rule"
        />
        <Stat
          term={t("usage-cache")}
          value={input ? share(totals.units.cached_input_tokens ?? 0, input) : "-"}
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
  attention = false,
  className,
}: {
  term: string;
  value: string;
  detail: string;
  attention?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("grid content-start gap-1 p-5 sm:p-6", className)}>
      <p className="caption">{term}</p>
      <p className="text-[1.65rem] leading-tight font-semibold tracking-[-0.02em] text-ink">{value}</p>
      <p className={cn("text-meta", attention ? "text-amber" : "text-ink-muted")}>{detail}</p>
    </div>
  );
}
