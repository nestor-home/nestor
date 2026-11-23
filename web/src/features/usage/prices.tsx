/** How each model is valued, beside what it cost over the period: billed by its provider, priced by the
 * configuration or the public list, free on the house's own machine, or unknown until a price is set. */
import { useQuery } from "@tanstack/react-query";
import { type ModelPrice, type UsagePeriod, type UsageUnit, usageGroupsQuery, usagePricesQuery } from "@/api";
import { BrandTile } from "@/components/marks";
import { Section } from "@/components/page";
import { Tag } from "@/components/status";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { capital, cn } from "@/lib/utils";
import { modelBrand } from "./dimensions";
import { money, rate } from "./format";
import { queryOf, type UsageSearch } from "./search";
import { priceSource } from "./sources";

export function Prices({ period, only }: { period: UsagePeriod; only: UsageSearch["only"] }) {
  const t = useT();
  const prices = useQuery(usagePricesQuery).data;
  // the same reading as the models' ranking: what each spent, and how many of its calls are of unknown cost
  const spent = useQuery(usageGroupsQuery({ ...queryOf(period, only, "consumer"), by: "consumer" })).data?.groups;
  if (!prices) return null;
  return (
    <Section title={t("usage-prices")}>
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
        {prices.prices.map((price) => {
          const totals = spent?.find((g) => g.key === price.consumer)?.totals;
          return (
            <Card key={price.consumer} price={price} spent={totals?.cost_nusd ?? 0} unknown={totals?.unknown ?? 0} />
          );
        })}
      </ul>
    </Section>
  );
}

function Card({ price, spent, unknown }: { price: ModelPrice; spent: number; unknown: number }) {
  const t = useT();
  const brand = modelBrand(price.model, price.provider);
  const listed = Object.entries(price.prices) as [UsageUnit, number][];
  const missing = !price.local && !price.source && unknown > 0;
  const how = price.local
    ? t("usage-source-local")
    : price.source
      ? priceSource(price.source)
      : t(missing ? "usage-price-missing" : "usage-source-reported");
  return (
    <li className="surface flex flex-col gap-4 p-5">
      <div className="flex items-start gap-3">
        {brand ? <BrandTile brand={brand} /> : null}
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
              <Tag key={unit}>{t(`usage-rate-${unit}`, { price: rate(amount) })}</Tag>
            ))}
            {unknown ? <Tag tone="attention">{t("usage-unknown-calls", { count: unknown })}</Tag> : null}
          </span>
        ) : null}
      </div>
    </li>
  );
}
