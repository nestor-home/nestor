import { animateDither, type DitherShape, drawDither } from "@nestor-home/character";
import { cn } from "@/lib/utils";

/**
 * Nestor's signature texture, as on the site (`Dither.astro`): the box carries the layout given by
 * `className`, the canvas fills it and is drawn by the shared `drawDither`, again whenever the box
 * is resized or the theme flips. A change of shape or density mounts a new canvas. `animated`, it
 * breathes through the shared `animateDither` (still when the reader asked for less motion).
 */
function attach(canvas: HTMLCanvasElement, animated: boolean) {
  const draw = () => drawDither(canvas);
  let stop: (() => void) | null = null;
  if (animated) stop = animateDither(canvas);
  else draw();
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

const attachStill = (canvas: HTMLCanvasElement) => attach(canvas, false);
const attachAnimated = (canvas: HTMLCanvasElement) => attach(canvas, true);

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
        ref={animated ? attachAnimated : attachStill}
        data-shape={shape}
        data-from={from}
        data-to={to}
        data-dot={dot}
        className="absolute inset-0 block h-full w-full"
      />
    </div>
  );
}
