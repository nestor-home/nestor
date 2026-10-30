import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * Nestor's signature texture: an ordered (Bayer 8×8) dither drawn once per size on a canvas, in the
 * current text colour, with square dots aligned to device pixels so it stays crisp at every DPR.
 * It is static (no animation), redrawn only when the element is resized or the theme flips.
 */
const BAYER = [
  [0, 32, 8, 40, 2, 34, 10, 42],
  [48, 16, 56, 24, 50, 18, 58, 26],
  [12, 44, 4, 36, 14, 46, 6, 38],
  [60, 28, 52, 20, 62, 30, 54, 22],
  [3, 35, 11, 43, 1, 33, 9, 41],
  [51, 19, 59, 27, 49, 17, 57, 25],
  [15, 47, 7, 39, 13, 45, 5, 37],
  [63, 31, 55, 23, 61, 29, 53, 21],
];

export type DitherShape = "ramp-right" | "ramp-left" | "ramp-down" | "ramp-up" | "field" | "vignette";

/** Density in [0, 1] of the texture at (u, v) in [0, 1]². */
function density(shape: DitherShape, u: number, v: number, from: number, to: number): number {
  const mix = (t: number) => from + (to - from) * t;
  switch (shape) {
    case "ramp-right":
      return mix(u);
    case "ramp-left":
      return mix(1 - u);
    case "ramp-down":
      return mix(v);
    case "ramp-up":
      return mix(1 - v);
    case "vignette": {
      const d = Math.min(1, Math.hypot(u - 0.5, v - 0.5) * 2);
      return mix(d);
    }
    default:
      return from;
  }
}

export function Dither({
  shape = "ramp-right",
  from = 0,
  to = 0.6,
  dot = 2,
  className,
}: {
  shape?: DitherShape;
  from?: number;
  to?: number;
  dot?: number; // CSS pixels per dot
  className?: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || typeof ResizeObserver === "undefined") return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const draw = () => {
      const ratio = window.devicePixelRatio || 1;
      const cell = Math.max(1, Math.round(dot * ratio));
      const { width, height } = canvas.getBoundingClientRect();
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = getComputedStyle(canvas).color;
      const cols = Math.ceil(canvas.width / cell);
      const rows = Math.ceil(canvas.height / cell);
      for (let y = 0; y < rows; y++) {
        const row = BAYER[y % 8] as number[];
        for (let x = 0; x < cols; x++) {
          const threshold = ((row[x % 8] as number) + 0.5) / 64;
          if (density(shape, x / Math.max(1, cols - 1), y / Math.max(1, rows - 1), from, to) > threshold) {
            context.fillRect(x * cell, y * cell, cell, cell);
          }
        }
      }
    };
    draw();
    const resize = new ResizeObserver(draw);
    resize.observe(canvas);
    const theme = new MutationObserver(draw);
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const scheme = matchMedia?.("(prefers-color-scheme: dark)");
    scheme?.addEventListener("change", draw);
    return () => {
      resize.disconnect();
      theme.disconnect();
      scheme?.removeEventListener("change", draw);
    };
  }, [shape, from, to, dot]);

  // biome-ignore lint/a11y/noAriaHiddenOnFocusable: a canvas is not focusable; the texture is decoration
  return <canvas ref={ref} aria-hidden="true" className={cn("pointer-events-none block text-ink", className)} />;
}
