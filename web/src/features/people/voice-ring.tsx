/**
 * The ring of texture around Nestor while a voice is recorded: a fifth more of it lights up in ember
 * with each phrase kept. It breathes like the rest of the texture, and fills at once, still, when
 * the reader asked for less motion.
 */
import { BAYER, breathing } from "@nestor-home/character";
import { type ReactNode, useEffect, useRef } from "react";

const DOT = 3; // CSS pixels per dot
const FRAME_MS = 80;

function draw(canvas: HTMLCanvasElement, progress: number, breath: number): void {
  const context = canvas.getContext("2d");
  if (!context) return;
  const ratio = window.devicePixelRatio || 1;
  const width = Math.round(canvas.clientWidth * ratio);
  const height = Math.round(canvas.clientHeight * ratio);
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  context.clearRect(0, 0, width, height);
  const dot = Math.max(1, Math.round(DOT * ratio));
  const outer = Math.min(width, height) / 2;
  const inner = outer * 0.82;
  const lit = getComputedStyle(canvas).color;
  const unlit = canvas.parentElement ? getComputedStyle(canvas.parentElement).color : lit;
  for (let y = 0; y < Math.ceil(height / dot); y++) {
    for (let x = 0; x < Math.ceil(width / dot); x++) {
      const dx = (x + 0.5) * dot - width / 2;
      const dy = (y + 0.5) * dot - height / 2;
      const r = Math.hypot(dx, dy);
      if (r < inner || r > outer) continue;
      const turn = (Math.atan2(dx, -dy) + 2 * Math.PI) % (2 * Math.PI);
      const filled = turn / (2 * Math.PI) < progress;
      const edge = Math.abs((r - inner) / (outer - inner) - 0.5) * 2; // 0 in the middle of the band, 1 at its edges
      const density = (filled ? 0.85 * breath : 0.3) * (1 - 0.6 * edge * edge);
      if ((BAYER[y % 8]?.[x % 8] ?? 0) / 64 >= density) continue;
      context.fillStyle = filled ? lit : unlit;
      context.fillRect(x * dot, y * dot, dot, dot);
    }
  }
}

export function VoiceRing({
  taken,
  total,
  label,
  children,
}: {
  taken: number;
  total: number;
  label: string; // what the ring counts, for screen readers
  children: ReactNode;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const progress = total ? taken / total : 0;
  const target = useRef(progress);
  const redraw = useRef<() => void>(() => undefined);
  target.current = progress;

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let shown = target.current;
    if (reduced) {
      redraw.current = () => draw(element, target.current, 1);
      redraw.current();
      return () => {
        redraw.current = () => undefined;
      };
    }
    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (now - last < FRAME_MS) return;
      last = now;
      shown += (target.current - shown) * 0.35;
      if (Math.abs(target.current - shown) < 0.002) shown = target.current;
      draw(element, shown, breathing(now / 1000));
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (progress >= 0) redraw.current();
  }, [progress]);

  return (
    <div className="relative grid size-52 place-items-center text-ink/25">
      <div aria-hidden="true" className="absolute inset-0">
        <canvas ref={canvas} className="block size-full text-ember" />
      </div>
      <progress className="sr-only" value={taken} max={total} aria-label={label} />
      <div className="relative">{children}</div>
    </div>
  );
}
