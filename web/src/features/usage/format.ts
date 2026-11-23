/** Amounts and quantities as the spending screen shows them, in the reader's language. */
import { activeLocale } from "@/i18n";

const NANO = 1e9;

/** Dollars to the cent; below a cent, two significant digits, so that a small call stays visible ($0.0042). */
export function money(nusd: number): string {
  const dollars = nusd / NANO;
  const small = dollars > 0 && dollars < 0.01;
  return new Intl.NumberFormat(activeLocale(), {
    style: "currency",
    currency: "USD",
    ...(small ? { maximumSignificantDigits: 2 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  }).format(dollars);
}

/** A round amount for an axis: $0, $0.50, $12, $1.2K. */
export function moneyTick(nusd: number): string {
  const dollars = nusd / NANO;
  return new Intl.NumberFormat(activeLocale(), {
    style: "currency",
    currency: "USD",
    notation: dollars >= 1000 ? "compact" : "standard",
    maximumFractionDigits: dollars >= 10 || dollars === 0 ? 0 : 2,
  }).format(dollars);
}

/** A count, compact past ten thousand: 1,284 · 12.9K · 4.2M. */
export function count(n: number): string {
  return new Intl.NumberFormat(activeLocale(), {
    notation: n >= 10_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(n);
}

/** A share, without a decimal past 10 %: 4.5 % · 62 %. */
export function share(part: number, whole: number): string {
  const ratio = whole > 0 ? part / whole : 0;
  return new Intl.NumberFormat(activeLocale(), {
    style: "percent",
    maximumFractionDigits: ratio < 0.1 && ratio > 0 ? 1 : 0,
  }).format(ratio);
}

/** Clean ticks from 0 to a little over `max`: 1, 2 or 5 times a power of ten. */
export function ticks(max: number, wanted = 4): number[] {
  if (max <= 0) return [0];
  const rough = max / wanted;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? 10 * power;
  const top = Math.ceil(max / step) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
}

/** A price as providers write it: to the cent, three significant digits below a dollar ($0.00367). */
export function rate(dollars: number): string {
  return new Intl.NumberFormat(activeLocale(), {
    style: "currency",
    currency: "USD",
    ...(dollars < 1 ? { maximumSignificantDigits: 3 } : { minimumFractionDigits: 0, maximumFractionDigits: 2 }),
  }).format(dollars);
}
