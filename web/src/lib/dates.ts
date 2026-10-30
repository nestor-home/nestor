/** Dates and times in the active locale (Intl), in the browser's timezone. */
import { activeLocale, tr } from "@/i18n/runtime";

const format = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(activeLocale(), options);

/** `14:05:12`: the clock of a log line, always 24 h so columns line up. */
export function clock(iso: string): string {
  return format({ hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(new Date(iso));
}

/** `14:05` */
export function hourMinute(iso: string): string {
  return format({ hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
}

/** `today 14:05`, `yesterday 09:12`, `28 Oct 09:12`, `28 Oct 2025 09:12`. */
export function moment(iso: string, now: Date = new Date()): string {
  const at = new Date(iso);
  const time = hourMinute(iso);
  if (sameDay(at, now)) return tr("time-today", { time });
  if (sameDay(at, yesterdayOf(now))) return tr("time-yesterday", { time });
  const day = format({
    day: "numeric",
    month: "short",
    ...(at.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
  }).format(at);
  return tr("time-day", { day, time });
}

/** The heading of a day in the journal: `today`, `yesterday`, `Tuesday 28 October`. */
export function dayLabel(iso: string, now: Date = new Date()): string {
  const at = new Date(iso);
  if (sameDay(at, now)) return tr("day-today");
  if (sameDay(at, yesterdayOf(now))) return tr("day-yesterday");
  return format({
    weekday: "long",
    day: "numeric",
    month: "long",
    ...(at.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
  }).format(at);
}

/** `4 min 05 s` until `iso`, never negative. */
export function remaining(iso: string, now: Date = new Date()): string {
  const seconds = Math.max(0, Math.round((new Date(iso).getTime() - now.getTime()) / 1000));
  return tr("remaining", { minutes: Math.floor(seconds / 60), seconds: String(seconds % 60).padStart(2, "0") });
}

function yesterdayOf(now: Date): Date {
  const d = new Date(now);
  d.setDate(now.getDate() - 1);
  return d;
}

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** Midnight today, local time, as ISO. */
export function startOfToday(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}
