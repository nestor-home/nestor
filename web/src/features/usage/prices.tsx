/** How each model is valued, beside what it cost over the period: billed by its provider, priced by the
 * configuration or the public list, free on the house's own machine, or unknown until a price is set. */
import { useQuery } from "@tanstack/react-query";
import { type ModelPrice, type UsageUnit, usageGroupsQuery, usagePricesQuery } from "@/api";
import { Section } from "@/components/page";
import { Tag } from "@/components/status";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { BrandMark, brandOf } from "@/lib/brands";
import { cn } from "@/lib/utils";
import { priceSource } from "./call-sheet";
import { capital, makerOf } from "./dimensions";
import { money } from "./format";
import { filtersOf, type Period, type UsageSearch } from "./search";

export function Prices({ period, only }: { period: Period; only: UsageSearch["only"] }) {
  const t = useT();
  const prices = useQuery(usagePricesQuery).data;
  const filters = filtersOf(period, only, "consumer");
  const spent = useQuery(usageGroupsQuery({ ...filters, by: "consumer" })).data?.groups ?? [];
  const unknown = useQuery(usageGroupsQuery({ ...filters, basis: ["unknown"], by: "consumer" })).data?.groups ?? [];
  if (!prices) return null;
  return (
    <Section title={t("usage-prices")}>
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
        {prices.prices.map((price) => (
          <Card
            key={price.consumer}
            price={price}
            spent={spent.find((g) => g.key === price.consumer)?.totals.cost_nusd ?? 0}
            unknown={unknown.find((g) => g.key === price.consumer)?.totals.calls ?? 0}
          />
        ))}
      </ul>
    </Section>
  );
}

function Card({ price, spent, unknown }: { price: ModelPrice; spent: number; unknown: number }) {
  const t = useT();
  const brand = brandOf(makerOf(price.model, price.provider));
  const listed = Object.entries(price.prices) as [UsageUnit, number][];
  const missing = !price.local && !price.source && unknown > 0;
  const how = price.local
    ? t("usage-source-local")
    : price.source
      ? priceSource(price.source, t)
      : missing
        ? t("usage-price-missing")
        : t("usage-source-reported");
  return (
    <li className="surface flex flex-col gap-4 p-5">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-paper-sunken">
          {brand ? <BrandMark brand={brand} label={false} className="size-5" /> : null}
        </span>
        <span className="min-w-0">
          <span className="block truncate font-serif text-title leading-tight text-ink">{price.consumer}</span>
          <span className="block truncate text-meta text-ink-faint">
            {capital(tr("usage-kind", { kind: price.kind }))}
            {price.model ? ` · ${price.model}` : ""}
          </span>
        </span>
      </div>
      <p className="text-[1.5rem] leading-none font-semibold tracking-[-0.02em] text-ink">{money(spent)}</p>
      <div className="mt-auto grid gap-2">
        <p className={cn("text-meta", missing ? "text-amber" : "text-ink-muted")}>{how}</p>
        {listed.length || unknown ? (
          <span className="flex flex-wrap gap-1.5">
            {listed.map(([unit, amount]) => (
              <Tag key={unit}>
                {t(`usage-rate-${unit}`, { price: rate(unit === "audio_seconds" ? amount * 60 : amount) })}
              </Tag>
            ))}
            {unknown ? <Tag tone="attention">{t("usage-unknown-calls", { count: unknown })}</Tag> : null}
          </span>
        ) : null}
      </div>
    </li>
  );
}

/** A price as written: to the cent, or three significant digits below a dollar. */
function rate(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    ...(amount < 1 ? { maximumSignificantDigits: 3 } : { minimumFractionDigits: 0, maximumFractionDigits: 2 }),
  }).format(amount);
}
