/** One call, opened from the list: what it consumed and cost, how that is known, on whose behalf and why. */
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import type { UsageCall } from "@/api";
import { BrandTile } from "@/components/marks";
import { SheetPanel, SideSheet } from "@/components/overlay-form";
import { Fact, Facts, RowList } from "@/components/page";
import { Tag } from "@/components/status";
import { activeLocale, useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { kindName } from "@/lib/brands";
import { duration } from "@/lib/time";
import { capital } from "@/lib/utils";
import { type Dimensions, modelBrand } from "./dimensions";
import { count, money } from "./format";
import { costSource } from "./sources";

export function CallSheet({
  call,
  open,
  onOpenChange,
  onClosed,
  dimensions,
}: {
  call: UsageCall | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onClosed: () => void;
  dimensions: Dimensions;
}) {
  return (
    <SideSheet open={open} onOpenChange={onOpenChange} onClosed={onClosed}>
      {call ? <Opened call={call} dimensions={dimensions} /> : null}
    </SideSheet>
  );
}

function Opened({ call, dimensions }: { call: UsageCall; dimensions: Dimensions }) {
  const t = useT();
  const brand = modelBrand(call.served, call.provider);
  const at = new Intl.DateTimeFormat(activeLocale(), { dateStyle: "full", timeStyle: "short" }).format(
    new Date(call.at),
  );
  const units = Object.entries(call.units).filter(([, n]) => n);
  const person = call.person?.id ?? null;
  return (
    <SheetPanel
      mark={brand ? <BrandTile brand={brand} size="sm" /> : undefined}
      kind={t("usage-call-kind", { consumer: call.consumer })}
      title={capital(tr("usage-purpose", { purpose: call.purpose }))}
      description={at}
      actions={
        call.session ? (
          <Link
            to="/journal"
            search={{ session: call.session }}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-rule-strong bg-paper-raised px-3 text-body text-ink hover:border-ink"
          >
            {t("usage-call-journal")}
            <ArrowUpRight aria-hidden="true" className="size-4" />
          </Link>
        ) : undefined
      }
    >
      <div className="surface grid gap-1 p-5">
        <p className="caption">{t("usage-call-cost")}</p>
        <p className="text-[2.25rem] leading-none font-semibold tracking-[-0.02em] text-ink">
          {call.cost_nusd === null || call.cost_nusd === undefined
            ? capital(tr("usage-basis", { basis: "unknown" }))
            : money(call.cost_nusd)}
        </p>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-meta text-ink-muted">
          {call.basis === "unknown" ? <Tag tone="attention">{tr("usage-basis", { basis: call.basis })}</Tag> : null}
          {costSource(call.basis, call.price)}
        </p>
      </div>
      <Facts narrow>
        <Fact term={t("usage-call-who")}>
          <span className="flex items-center gap-2">
            {dimensions.mark("person", person)}
            {dimensions.label("person", person)}
          </span>
        </Fact>
        {call.channel ? (
          <Fact term={t("usage-call-where")}>
            {kindName(call.channel)}
            {call.medium ? ` · ${t(`usage-medium-${call.medium}`)}` : ""}
          </Fact>
        ) : null}
        <Fact term={t("usage-call-model")}>
          <span className="font-medium text-ink">{call.consumer}</span>
          {call.served ? <span className="block font-mono text-micro text-ink-muted">{call.served}</span> : null}
        </Fact>
        <Fact term={t("usage-call-provider")}>{dimensions.label("provider", call.provider)}</Fact>
        <Fact term={t("usage-call-outcome")}>
          {capital(tr("usage-outcome", { outcome: call.outcome }))} · {duration(call.duration_ms / 1000)}
        </Fact>
        {call.origin ? (
          <Fact term={t("usage-call-origin")}>
            <span className="font-mono text-micro">{call.origin}</span>
          </Fact>
        ) : null}
      </Facts>
      {units.length ? (
        <div className="grid gap-2">
          <p className="caption">{t("usage-call-units")}</p>
          <RowList>
            {units.map(([unit, n]) => (
              <li key={unit} className="flex items-baseline justify-between gap-4 px-4 py-2.5 text-meta">
                <span className="text-ink-muted">{capital(tr("usage-unit", { unit }))}</span>
                <span className="font-medium text-ink tabular">{count(Math.round((n ?? 0) * 10) / 10)}</span>
              </li>
            ))}
          </RowList>
        </div>
      ) : null}
    </SheetPanel>
  );
}
