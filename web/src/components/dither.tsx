import { type DitherShape, drawDither } from "@nestor-home/character";
import { cn } from "@/lib/utils";

/**
 * Nestor's signature texture, as on the site (`Dither.astro`): the box carries the layout given by
 * `className`, the canvas fills it and is drawn by the shared `drawDither`, again whenever the box
 * is resized or the theme flips. A change of shape or density mounts a new canvas. `animated`, it
 * breathes: its density swells and ebbs, so dots light up and go out across it (still when the
 * reader asked for less motion).
 */
const FRAME_MS = 80; // a dot texture needs no more than about twelve frames a second
const BREATH_S = 2.4;

function breathe(canvas: HTMLCanvasElement, from: number, to: number) {
  let frame = 0;
  let last = 0;
  const tick = (now: number) => {
    frame = requestAnimationFrame(tick);
    if (now - last < FRAME_MS) return;
    last = now;
    const swell = 0.7 + 0.3 * Math.sin(((now / 1000) * 2 * Math.PI) / BREATH_S);
    canvas.dataset.from = String(from * swell);
    canvas.dataset.to = String(to * swell);
    drawDither(canvas);
  };
  frame = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(frame);
}

function attach(canvas: HTMLCanvasElement, animated: boolean) {
  const draw = () => drawDither(canvas);
  draw();
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const stop = animated && !still ? breathe(canvas, Number(canvas.dataset.from), Number(canvas.dataset.to)) : null;
  const resize = new ResizeObserver(draw);
  resize.observe(canvas);
  const theme = new MutationObserver(draw);
  theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  const scheme = matchMedia("(prefers-color-scheme: dark)");
  scheme.addEventListener("change", draw);
  return () => {
    stop?.();
    resize.disconnect();
    theme.disconnect();
    scheme.removeEventListener("change", draw);
  };
}

export function Dither({
  shape = "ramp-right",
  from = 0,
  to = 0.6,
  dot = 2,
  animated = false,
  className,
}: {
  shape?: DitherShape;
  from?: number;
  to?: number;
  dot?: number; // CSS pixels per dot
  animated?: boolean;
  className?: string;
}) {
  const positioned = /\b(absolute|fixed)\b/.test(className ?? "");
  return (
    <div aria-hidden="true" className={cn("pointer-events-none text-ink", !positioned && "relative", className)}>
      <canvas
        key={`${shape} ${from} ${to} ${dot} ${animated}`}
        ref={(canvas) => (canvas ? attach(canvas, animated) : undefined)}
        data-shape={shape}
        data-from={from}
        data-to={to}
        data-dot={dot}
        className="absolute inset-0 block h-full w-full"
      />
    </div>
  );
}
