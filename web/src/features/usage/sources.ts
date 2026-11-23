/** Where a cost comes from, as people read it: the provider's bill, the house's own machine, a price and where it
 * was found, or nothing known. */
import type { CostBasis } from "@/api";
import { tr } from "@/i18n/runtime";
import { calendarDay } from "@/lib/dates";

const CATALOGUE = "catalogue:";

/** A price's source (`config`, `catalogue:<date>`). */
export function priceSource(price: string): string {
  if (price.startsWith(CATALOGUE))
    return tr("usage-source-catalogue", { date: calendarDay(price.slice(CATALOGUE.length)) });
  return tr("usage-source-config");
}

/** How a cost is known, from its basis and, for a priced one, its price's source. */
export function costSource(basis: CostBasis, price: string | null | undefined): string {
  if (price) return priceSource(price);
  return tr(
    basis === "free" ? "usage-source-local" : basis === "unknown" ? "usage-price-missing" : "usage-source-reported",
  );
}
