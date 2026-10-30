/** Relative times and durations in the active locale. */
import { activeLocale, tr } from "@/i18n/runtime";

/** `just now`, `3 min ago`, `in 2 hr`, `yesterday`, then the date: what people say. */
export function ago(iso: string, now: Date = new Date()): string {
  const relative = new Intl.RelativeTimeFormat(activeLocale(), { numeric: "auto", style: "short" });
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return tr("time-just-now");
  if (abs < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (abs < 86_400) return relative.format(Math.round(seconds / 3600), "hour");
  if (abs < 7 * 86_400) return relative.format(Math.round(seconds / 86_400), "day");
  return new Intl.DateTimeFormat(activeLocale(), { day: "numeric", month: "short" }).format(new Date(iso));
}

/** `0,8 s`, `42 s`, `3 min 05`, `1 h 12`: a duration in the units people read. */
export function duration(seconds: number): string {
  if (seconds < 1) return tr("duration-ms", { ms: Math.round(seconds * 1000) });
  if (seconds < 60) {
    const value = new Intl.NumberFormat(activeLocale(), { maximumFractionDigits: seconds < 10 ? 1 : 0 }).format(
      seconds,
    );
    return tr("duration-s", { seconds: value });
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return tr("duration-min", { minutes, seconds: String(Math.round(seconds % 60)).padStart(2, "0") });
  return tr("duration-h", { hours: Math.floor(minutes / 60), minutes: String(minutes % 60).padStart(2, "0") });
}

export function number(n: number): string {
  return new Intl.NumberFormat(activeLocale()).format(n);
}
