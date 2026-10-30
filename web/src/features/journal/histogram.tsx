import { useRef, useState } from "react";
import type { JournalFacets } from "@/api";
import { useT } from "@/i18n";
import { moment } from "@/lib/dates";
import { cn } from "@/lib/utils";

/**
 * Activity over the selected time, one bar per bucket. Dragging across bars zooms the journal to
 * that span (the time-range picker does the same from the keyboard).
 */
export function Histogram({
  histogram,
  onRange,
}: {
  histogram: JournalFacets["histogram"] | undefined;
  onRange: (from: string, to: string) => void;
}) {
  const t = useT();
  const ref = useRef<SVGSVGElement>(null);
  const [brush, setBrush] = useState<[number, number] | null>(null);
  if (!histogram) return <div className="h-14" />;
  const { counts, from, bucket_s } = histogram;
  const max = Math.max(1, ...counts);
  const n = counts.length;
  const start = new Date(from).getTime();
  const bucketAt = (clientX: number) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return 0;
    return Math.min(n - 1, Math.max(0, Math.floor(((clientX - box.left) / box.width) * n)));
  };
  const finish = () => {
    if (brush) {
      const [a, b] = brush[0] <= brush[1] ? brush : [brush[1], brush[0]];
      onRange(
        new Date(start + a * bucket_s * 1000).toISOString(),
        new Date(start + (b + 1) * bucket_s * 1000).toISOString(),
      );
    }
    setBrush(null);
  };
  const low = brush ? Math.min(...brush) : -1;
  const high = brush ? Math.max(...brush) : -1;
  const total = counts.reduce((a, b) => a + b, 0);
  return (
    <figure className="select-none">
      <svg
        ref={ref}
        role="img"
        aria-label={t("jr-histogram-label", { count: total, from: moment(histogram.from), to: moment(histogram.to) })}
        viewBox={`0 0 ${n * 4} 40`}
        preserveAspectRatio="none"
        className="h-12 w-full cursor-crosshair touch-none"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          const i = bucketAt(e.clientX);
          setBrush([i, i]);
        }}
        onPointerMove={(e) => brush && setBrush([brush[0], bucketAt(e.clientX)])}
        onPointerUp={finish}
      >
        {counts.map((c, i) => {
          const h = c ? Math.max(2, (c / max) * 38) : 0.6;
          return (
            <rect
              // biome-ignore lint/suspicious/noArrayIndexKey: buckets are positional
              key={i}
              x={i * 4 + 0.5}
              y={40 - h}
              width={3}
              height={h}
              className={cn(i >= low && i <= high ? "fill-ember" : c ? "fill-ink/35" : "fill-rule-strong")}
            />
          );
        })}
      </svg>
      <figcaption className="mt-1 flex justify-between font-mono text-[0.66rem] text-ink-faint tabular">
        <span>{moment(histogram.from)}</span>
        <span>{moment(histogram.to)}</span>
      </figcaption>
    </figure>
  );
}
