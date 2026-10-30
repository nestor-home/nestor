/**
 * The day on one 24-hour ribbon: a mark per conversation, per message the agent delivered, per task,
 * watch, memory and failure, each a link to its chain in the journal; quiet hours shaded, the
 * present marked. Marks of the same kind stack upward when they would overlap.
 */
import { Link, type LinkProps } from "@tanstack/react-router";
import { useT } from "@/i18n";
import { hourMinute } from "@/lib/dates";
import { usePeopleNames } from "@/lib/people";
import { cn } from "@/lib/utils";
import type { Mark, MarkKind } from "./mind";

const ROW: Record<MarkKind, number> = { conversation: 0, delivery: 1, task: 2, watch: 2, memory: 3, problem: 3 };

const TONE: Record<MarkKind, string> = {
  conversation: "bg-ink",
  delivery: "bg-ember",
  task: "bg-kind-task",
  watch: "bg-kind-watch",
  memory: "bg-sage",
  problem: "bg-brick",
};

const DAY = 24 * 60;

function linkOf(mark: Mark): LinkProps {
  const { item } = mark;
  if (mark.kind === "conversation" && item.links.session)
    return { to: "/journal", search: { session: item.links.session } };
  if (mark.kind === "task" && item.links.task) return { to: "/tasks/$taskId", params: { taskId: item.links.task } };
  if (mark.kind === "watch" && item.links.watch)
    return { to: "/watches/$watchId", params: { watchId: item.links.watch } };
  return { to: "/journal", search: { event: item.id } };
}

export function DayRibbon({
  marks,
  quiet,
  now,
}: {
  marks: Mark[];
  quiet: { from: number; to: number } | null;
  now: Date;
}) {
  const t = useT();
  const name = usePeopleNames();
  const nowMinute = now.getHours() * 60 + now.getMinutes();
  const pct = (minute: number) => `${(minute / DAY) * 100}%`;
  const shades = quiet
    ? quiet.from <= quiet.to
      ? [[quiet.from, quiet.to]]
      : [
          [0, quiet.to],
          [quiet.from, DAY],
        ]
    : [];
  // marks closer than this (in minutes) on the same row are lifted a little, to stay clickable
  const lane = new Map<string, number>();
  const last: Record<number, number[]> = {};
  for (const m of marks) {
    const row = ROW[m.kind];
    const ends = last[row] ?? [];
    last[row] = ends;
    let level = ends.findIndex((end) => m.minute - end > 14);
    if (level === -1) level = ends.length;
    ends[level] = m.minute;
    lane.set(m.key, Math.min(level, 2));
  }
  const tell = (m: Mark) =>
    t(`home-mark-${m.kind}`, {
      time: hourMinute(m.at),
      people: m.people.map((p) => name(p)).join(", ") || "—",
      count: m.count,
      where: m.room ?? m.channels.join(", ") ?? "",
    });
  return (
    <div>
      <div className="relative h-36 overflow-hidden rounded-md border border-rule bg-paper-raised">
        {shades.map(([from = 0, to = 0]) => (
          <div
            key={from}
            className="absolute inset-y-0 bg-[repeating-linear-gradient(135deg,var(--rule)_0_1px,transparent_1px_6px)]"
            style={{ left: pct(from), width: pct(to - from) }}
          />
        ))}
        {[0, 3, 6, 9, 12, 15, 18, 21].map((h) => (
          <div key={h} className="absolute inset-y-0 border-l border-rule" style={{ left: pct(h * 60) }}>
            <span className="absolute bottom-1 left-1 font-mono text-[0.62rem] text-ink-faint">{`${h}h`}</span>
          </div>
        ))}
        <div className="absolute inset-y-0 border-l border-ember" style={{ left: pct(nowMinute) }}>
          <span className="absolute top-1 left-1 font-mono text-[0.62rem] text-ember">
            {hourMinute(now.toISOString())}
          </span>
        </div>
        <ol aria-label={t("home-day-marks", { count: marks.length })} className="absolute inset-0">
          {marks.map((m) => (
            <li
              key={m.key}
              className="absolute -translate-x-1/2"
              style={{ left: pct(m.minute), top: `${14 + ROW[m.kind] * 22 - (lane.get(m.key) ?? 0) * 7}%` }}
            >
              <Link
                {...linkOf(m)}
                aria-label={tell(m)}
                title={tell(m)}
                className="group grid place-items-center p-1 focus-visible:outline-2 focus-visible:outline-ember"
              >
                <span
                  className={cn(
                    "block rounded-full transition-transform group-hover:scale-150",
                    TONE[m.kind],
                    m.kind === "conversation" ? (m.count > 4 ? "size-3" : "size-2.5") : "size-2",
                    m.kind === "delivery" && "h-3.5 w-1.5 rounded-sm",
                  )}
                />
              </Link>
            </li>
          ))}
        </ol>
      </div>
      <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.68rem] text-ink-muted">
        {(["conversation", "delivery", "task", "watch", "memory", "problem"] as const).map((kind) => (
          <li key={kind} className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className={cn("size-2 rounded-full", TONE[kind])} />
            {t(`home-legend-${kind}`, { count: marks.filter((m) => m.kind === kind).length })}
          </li>
        ))}
        {quiet ? (
          <li className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-2.5 border border-rule bg-[repeating-linear-gradient(135deg,var(--rule-strong)_0_1px,transparent_1px_3px)]"
            />
            {t("home-legend-quiet")}
          </li>
        ) : null}
      </ul>
    </div>
  );
}
