/**
 * The spending charts, drawn by hand in SVG on the admin's own tokens: thin marks, a 2px gap of paper between
 * touching marks, hairline grids, text in ink and never in a series colour, and a tooltip on every mark that the
 * calls below and the legend repeat, so that nothing is only on hover.
 */
import { type ReactNode, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { UsageBeat, UsageGroup, UsageInterval, UsagePoint, UsageSpan } from "@/api";
import { activeLocale } from "@/i18n";
import { cn } from "@/lib/utils";
import { count, money, moneyTick, share, ticks } from "./format";

/** How wide the box is, as it changes. */
function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    setWidth(element.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(entry?.contentRect.width ?? 0));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** A moment as the household's clock shows it: the server writes it with the household's offset, so its wall clock
 * is read as written, whatever the browser's zone. */
const wall = (iso: string) => new Date(`${iso.slice(0, 19)}Z`);

/** The formatters of a locale, made once: a chart redraws on every move of the pointer. */
function formatters(locale: string) {
  const make = (options: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(locale, { ...options, timeZone: "UTC" });
  return {
    hour: make({ hour: "numeric" }),
    hourOfDay: make({ weekday: "short", hour: "numeric" }),
    day: make({ day: "numeric", month: "short" }),
    longDay: make({ weekday: "short", day: "numeric", month: "short" }),
    month: make({ month: "short", year: "numeric" }),
    weekday: make({ weekday: "short" }),
  };
}

type Formatters = ReturnType<typeof formatters>;

/** When a bucket starts, as people read it under the axis (`long`: atop a tooltip). */
function when(iso: string, every: UsageInterval, long: boolean, f: Formatters): string {
  const at = wall(iso);
  if (every === "hour") return (long ? f.hourOfDay : f.hour).format(at);
  if (every === "month") return f.month.format(at);
  return (long ? f.longDay : f.day).format(at);
}

// -- the tooltip ------------------------------------------------------------------------------------

export interface TipRow {
  key: string;
  colour: string;
  label: string;
  value: string;
}

/** A readout beside the pointer: its title, then the value first and the name after, keyed by a short stroke. */
function Tip({
  x,
  y,
  width,
  title,
  total,
  rows = [],
}: {
  x: number;
  y: number;
  width: number;
  title: string;
  total: string;
  rows?: TipRow[];
}) {
  const flip = x > width - 220;
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 w-max max-w-[15rem] rounded-xl bg-paper-raised px-3.5 py-3 text-meta shadow-(--lift-hover)"
      style={{ left: flip ? undefined : x + 14, right: flip ? width - x + 14 : undefined, top: Math.max(0, y - 12) }}
    >
      <p className="font-medium text-ink">{title}</p>
      <p className="mt-0.5 text-lead font-semibold text-ink tabular">{total}</p>
      {rows.length ? (
        <ul className="mt-2 grid gap-1">
          {rows.map((row) => (
            <li key={row.key} className="flex items-center gap-2">
              <span aria-hidden="true" className="h-0.5 w-3 shrink-0 rounded-full" style={{ background: row.colour }} />
              <span className="font-semibold text-ink tabular">{row.value}</span>
              <span className="min-w-0 truncate text-ink-muted">{row.label}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Where the pointer is in a chart's box, for its tooltip. */
function pointerIn(box: React.RefObject<HTMLElement | null>, event: React.PointerEvent) {
  const rect = box.current?.getBoundingClientRect();
  return rect ? { x: event.clientX - rect.left, y: event.clientY - rect.top } : null;
}

// -- spending over time: stacked columns --------------------------------------------------------------

const BUCKET_MS: Record<UsageInterval, number> = {
  hour: 3_600_000,
  day: 86_400_000,
  week: 7 * 86_400_000,
  month: 30 * 86_400_000,
};

export interface Series {
  key: string; // a dimension's value, `NONE` for calls without one, `OTHER_KEY` for the folded rest
  label: string;
  colour: string;
}

export const OTHER_KEY = "\u0000other";

export function StackedColumns({
  points,
  series,
  keyOf,
  span,
  label,
  onPick,
}: {
  points: UsagePoint[];
  series: Series[];
  /** which series a group belongs to: its own, or the folded rest */
  keyOf: (group: UsageGroup) => string;
  span: UsageSpan;
  label: string;
  onPick: (key: string) => void;
}) {
  const [box, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null);
  const f = useMemo(() => formatters(activeLocale()), []);
  const stacks = useMemo(
    () =>
      points.map((point) => {
        const parts = new Map<string, number>();
        for (const group of point.groups) {
          const key = keyOf(group);
          parts.set(key, (parts.get(key) ?? 0) + group.totals.cost_nusd);
        }
        return {
          point,
          start: new Date(point.start).getTime(),
          parts,
          total: [...parts.values()].reduce((a, b) => a + b, 0),
          calls: point.groups.reduce((sum, g) => sum + g.totals.calls, 0),
        };
      }),
    [points, keyOf],
  );
  const height = width < 480 ? 200 : 260;
  const left = 52;
  const plotWidth = Math.max(0, width - left - 4);
  const plotHeight = height - 34;
  const scale = ticks(Math.max(0, ...stacks.map((s) => s.total)));
  const top = scale.at(-1) || 1;
  // whole buckets: a week that began before the period is drawn in full, and today shows all its hours
  const step = BUCKET_MS[span.every];
  const from = Math.min(new Date(span.since).getTime(), ...stacks.map((s) => s.start));
  const end = Math.max(new Date(span.until).getTime(), ...stacks.map((s) => s.start + step));
  const to = span.every === "hour" ? Math.max(end, from + BUCKET_MS.day) : end;
  const scaleX = plotWidth / Math.max(1, to - from);
  const slot = step * scaleX;
  const barWidth = Math.max(2, Math.min(24, slot - (slot > 8 ? 4 : 2)));
  const xOf = (start: number) => left + (start - from) * scaleX;
  const yOf = (value: number) => 8 + plotHeight - (value / top) * plotHeight;
  const tickEvery = Math.max(1, Math.ceil(stacks.length / Math.max(2, Math.floor(plotWidth / 90))));
  const hovered = hover ? stacks[hover.index] : null;

  return (
    <div ref={box} className="relative w-full" onPointerLeave={() => setHover(null)}>
      {width > 0 ? (
        <svg width={width} height={height} role="img" aria-label={label} className="block overflow-visible">
          {scale.map((tick) => (
            <g key={tick}>
              <line x1={left} x2={width} y1={yOf(tick)} y2={yOf(tick)} stroke="var(--rule)" strokeWidth={1} />
              <text
                x={left - 8}
                y={yOf(tick)}
                dy="0.32em"
                textAnchor="end"
                className="fill-ink-faint text-micro tabular"
              >
                {moneyTick(tick)}
              </text>
            </g>
          ))}
          {stacks.map((stack, index) => {
            const x = xOf(stack.start) + Math.max(0, (slot - barWidth) / 2);
            const drawn = series.filter((s) => (stack.parts.get(s.key) ?? 0) > 0);
            let base = yOf(0);
            return (
              <g
                key={stack.point.start}
                opacity={hover !== null && hover.index !== index ? 0.45 : 1}
                className="transition-opacity duration-150"
                onPointerMove={(event) => {
                  const at = pointerIn(box, event);
                  if (at) setHover({ index, ...at });
                }}
              >
                <rect x={x - 3} y={8} width={barWidth + 6} height={plotHeight} fill="transparent" />
                {drawn.map((s, i) => {
                  const h = ((stack.parts.get(s.key) ?? 0) / top) * plotHeight;
                  const y = base - h;
                  base = y;
                  const segment = Math.max(0, h - (i > 0 ? 2 : 0)); // the 2px of paper between two segments
                  const r = i === drawn.length - 1 ? Math.min(4, segment, barWidth / 2) : 0;
                  return (
                    // biome-ignore lint/a11y/noStaticElementInteractions: the legend and the rankings do the same by keyboard
                    <path
                      key={s.key}
                      d={roundedTop(x, y, barWidth, segment, r)}
                      fill={s.colour}
                      className="cursor-pointer"
                      onClick={() => onPick(s.key)}
                    />
                  );
                })}
              </g>
            );
          })}
          {stacks.map((stack, index) =>
            index % tickEvery === 0 ? (
              <text
                key={stack.point.start}
                x={xOf(stack.start) + slot / 2}
                y={height - 6}
                textAnchor="middle"
                className="fill-ink-faint text-micro tabular"
              >
                {when(stack.point.start, span.every, false, f)}
              </text>
            ) : null,
          )}
        </svg>
      ) : (
        <div style={{ height }} />
      )}
      {hover && hovered ? (
        <Tip
          x={hover.x}
          y={hover.y}
          width={width}
          title={when(hovered.point.start, span.every, true, f)}
          total={money(hovered.total)}
          rows={series
            .filter((s) => (hovered.parts.get(s.key) ?? 0) > 0)
            .map((s) => ({
              key: s.key,
              colour: s.colour,
              label: s.label,
              value: money(hovered.parts.get(s.key) ?? 0),
            }))}
        />
      ) : null}
      <table className="sr-only">
        <caption>{label}</caption>
        <tbody>
          {stacks.map((stack) => (
            <tr key={stack.point.start}>
              <th scope="row">{when(stack.point.start, span.every, true, f)}</th>
              <td>{money(stack.total)}</td>
              <td>{count(stack.calls)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A column's path: square at the baseline, its top corners rounded by `r`. */
function roundedTop(x: number, y: number, w: number, h: number, r: number): string {
  if (h <= 0) return "";
  if (r <= 0) return `M${x},${y}h${w}v${h}h${-w}z`;
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}z`;
}

// -- ranked bars: who, which model, what for ---------------------------------------------------------------

const SHOWN = 5; // rows of a ranking before "n more"

export interface Ranked {
  key: string | null;
  label: string;
  mark: ReactNode;
  cost: number;
  detail: string;
}

/** Spending by one dimension, the costliest first: each row toggles the filter on its value. */
export function RankedBars({
  rows,
  active,
  onPick,
  more,
}: {
  rows: Ranked[];
  active: (key: string | null) => boolean;
  onPick: (key: string | null) => void;
  more: (n: number) => string;
}) {
  const [open, setOpen] = useState(false);
  const shown = open ? rows : rows.slice(0, SHOWN);
  const total = rows.reduce((sum, r) => sum + r.cost, 0);
  const max = Math.max(1, ...rows.map((r) => r.cost));
  const filtering = rows.some((r) => active(r.key));
  return (
    <div className="grid gap-1">
      {shown.map((row) => {
        const on = active(row.key);
        return (
          <button
            key={row.key ?? ""}
            type="button"
            aria-pressed={on}
            onClick={() => onPick(row.key)}
            className={cn(
              "group grid grid-cols-[1.5rem_minmax(0,1fr)_minmax(5rem,auto)] items-center gap-x-3 gap-y-1.5 rounded-lg px-2 py-2 text-left transition-colors",
              on ? "bg-paper-sunken" : "hover:bg-paper-sunken/60",
              filtering && !on && "opacity-55 hover:opacity-100",
            )}
          >
            <span className="grid size-6 place-items-center">{row.mark}</span>
            <span className="min-w-0 truncate text-body font-medium text-ink">{row.label}</span>
            <span className="text-right text-body font-semibold text-ink tabular">{money(row.cost)}</span>
            <span aria-hidden="true" className="col-start-2 h-1.5 overflow-hidden rounded-full bg-paper-sunken">
              <span
                className="block h-full rounded-full bg-ember transition-[width] duration-300 ease-(--ease)"
                style={{ width: `${(row.cost / max) * 100}%` }}
              />
            </span>
            <span className="text-right text-micro whitespace-nowrap text-ink-faint tabular">
              {share(row.cost, total)} · {row.detail}
            </span>
          </button>
        );
      })}
      {rows.length > SHOWN ? (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="justify-self-start rounded-lg px-2 py-1.5 text-meta font-medium text-ink-muted hover:text-ink"
        >
          {more(open ? 0 : rows.length - SHOWN)}
        </button>
      ) : null}
    </div>
  );
}

// -- when: hour by weekday ----------------------------------------------------------------------------------

export function HourByDay({ beats, label }: { beats: UsageBeat[]; label: string }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ beat: UsageBeat; x: number; y: number } | null>(null);
  const f = useMemo(() => formatters(activeLocale()), []);
  const byCell = useMemo(() => new Map(beats.map((b) => [b.weekday * 24 + b.hour, b])), [beats]);
  const max = Math.max(1, ...beats.map((b) => b.cost_nusd));
  // a Monday and the days after it, and the hours of a day, as the locale writes them
  const days = Array.from({ length: 7 }, (_, i) => f.weekday.format(new Date(Date.UTC(2026, 10, 2 + i))));
  const hourLabel = (hour: number) => f.hour.format(new Date(Date.UTC(2026, 0, 1, hour)));
  const left = 40;
  const gap = 2;
  const size = Math.max(6, Math.min(22, (width - left) / 24 - gap));
  const height = 7 * (size + gap) + 20;
  return (
    <div ref={box} className="relative w-full" onPointerLeave={() => setHover(null)}>
      {width > 0 ? (
        <svg width={width} height={height} role="img" aria-label={label} className="block">
          {days.map((day, row) => (
            <text
              key={day}
              x={left - 8}
              y={row * (size + gap) + size / 2}
              dy="0.32em"
              textAnchor="end"
              className="fill-ink-faint text-micro"
            >
              {day}
            </text>
          ))}
          {days.map((day, weekday) =>
            Array.from({ length: 24 }, (_, hour) => {
              const beat = byCell.get(weekday * 24 + hour);
              const level = beat ? Math.sqrt(beat.cost_nusd / max) : 0;
              return (
                <rect
                  // biome-ignore lint/suspicious/noArrayIndexKey: a cell is its hour of its day, the same on every render
                  key={`${day}-${hour}`}
                  x={left + hour * (size + gap)}
                  y={weekday * (size + gap)}
                  width={size}
                  height={size}
                  rx={3}
                  fill={
                    beat
                      ? `color-mix(in oklab, var(--series-1) ${Math.round(12 + level * 88)}%, var(--paper-raised))`
                      : "var(--paper-sunken)"
                  }
                  stroke={beat && hover?.beat === beat ? "var(--ink)" : "none"}
                  strokeWidth={1.5}
                  onPointerMove={(event) => {
                    const at = pointerIn(box, event);
                    if (at && beat) setHover({ beat, ...at });
                  }}
                />
              );
            }),
          )}
          {[0, 6, 12, 18].map((hour) => (
            <text
              key={hour}
              x={left + hour * (size + gap)}
              y={height - 4}
              className="fill-ink-faint text-micro tabular"
            >
              {hourLabel(hour)}
            </text>
          ))}
        </svg>
      ) : (
        <div style={{ height: 180 }} />
      )}
      {hover ? (
        <Tip
          x={hover.x}
          y={hover.y}
          width={width}
          title={`${days[hover.beat.weekday]} · ${hourLabel(hover.beat.hour)}`}
          total={money(hover.beat.cost_nusd)}
        />
      ) : null}
    </div>
  );
}

// -- small figures ----------------------------------------------------------------------------------------

/** The period's spending bucket by bucket, as a quiet line under its total, the last bucket lit. */
export function Sparkline({ values, className }: { values: number[]; className?: string }) {
  const [box, width] = useWidth<HTMLDivElement>();
  const height = 44;
  if (values.length < 2) return <div ref={box} className={className} style={{ height }} />;
  const max = Math.max(1, ...values);
  const step = width / (values.length - 1);
  const points = values.map((v, i) => [i * step, 4 + (height - 8) * (1 - v / max)] as const);
  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
  const last = points.at(-1) ?? [0, 0];
  return (
    <div ref={box} className={className} aria-hidden="true">
      {width > 0 ? (
        <svg width={width} height={height} aria-hidden="true" className="block overflow-visible">
          <path d={`${line}L${width},${height}L0,${height}Z`} fill="var(--ink)" opacity={0.06} />
          <path
            d={line}
            fill="none"
            stroke="var(--ink-faint)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <circle cx={last[0]} cy={last[1]} r={4} fill="var(--ember)" stroke="var(--paper-raised)" strokeWidth={2} />
        </svg>
      ) : null}
    </div>
  );
}

export interface Part {
  key: string;
  label: string;
  value: number;
  colour: string;
}

/** One whole split into parts: a thin bar, then the parts named under it. */
export function SegmentedBar({
  parts,
  label,
  format,
}: {
  parts: Part[];
  label: string;
  format: (n: number) => string;
}) {
  const total = parts.reduce((sum, p) => sum + p.value, 0);
  return (
    <div className="grid gap-3">
      <div role="img" aria-label={label} className="flex h-2 gap-0.5 overflow-hidden rounded-full">
        {parts
          .filter((p) => p.value > 0)
          .map((part) => (
            <span key={part.key} className="h-full" style={{ flexGrow: part.value, background: part.colour }} />
          ))}
      </div>
      <ul className="grid gap-1.5">
        {parts.map((part) => (
          <li key={part.key} className="flex items-center gap-2.5 text-meta">
            <span aria-hidden="true" className="size-2.5 shrink-0 rounded-[3px]" style={{ background: part.colour }} />
            <span className="min-w-0 flex-1 truncate text-ink-muted">{part.label}</span>
            <span className="font-medium text-ink tabular">{format(part.value)}</span>
            <span className="w-11 text-right text-ink-faint tabular">{share(part.value, total)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
