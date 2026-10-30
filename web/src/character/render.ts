/**
 * Nestor as SVG markup, framework-agnostic: a string any page can inline (Astro, React, plain
 * HTML). Its colours come only from CSS variables (`--ink`, `--paper`, `--ember`, with fallbacks),
 * so light and dark follow the page; `nestor.css` animates the states.
 */
import {
  BODY,
  BOW_AT,
  BOW_KNOT,
  BOW_VIEWBOX,
  BOW_WINGS,
  brow,
  EYE,
  EYES,
  happyEye,
  MOUTH,
  SIZE,
  SOUND,
  SPINNER,
  shutEye,
  THOUGHTS,
  TUFT,
  VIEWBOX,
} from "./geometry";

export const STATES = [
  "idle",
  "listening",
  "thinking",
  "speaking",
  "laughing",
  "sleeping",
  "working",
  "concerned",
] as const;
export type NestorState = (typeof STATES)[number];

export interface RenderOptions {
  state?: NestorState;
  /** pixels (or any CSS length); at 24 px and below the drawing drops its small details */
  size?: number | string;
  /** an accessible name; without one the drawing is decorative (aria-hidden) */
  label?: string;
  className?: string;
  id?: string;
  /** a soft flat shadow under it */
  ground?: boolean;
  /** extra attributes for the root element (data-*, style…), escaped */
  attributes?: Record<string, string>;
}

const escapeAttr = (text: string) => text.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

const bowPlacement = () => `transform="translate(${BOW_AT.x} ${BOW_AT.y}) scale(${BOW_AT.scale})"`;

/** The bow tie's shapes around (0, 0): classes for CSS colours, or written colours for stills. */
function bowShapes(wingClass?: string, knotClass?: string, wing?: string, knot?: string): string {
  const paint = (className?: string, colour?: string) =>
    `${className ? ` class="${className}"` : ""}${colour ? ` fill="${colour}"` : ""}`;
  return (
    BOW_WINGS.map((d) => `<path d="${d}"${paint(wingClass, wing)}/>`).join("") +
    `<rect x="${BOW_KNOT.x}" y="${BOW_KNOT.y}" width="${BOW_KNOT.width}" height="${BOW_KNOT.height}" rx="${BOW_KNOT.r}"${paint(knotClass, knot)}/>`
  );
}

export function renderNestor({
  state = "idle",
  size = SIZE,
  label,
  className = "",
  id,
  ground = false,
  attributes = {},
}: RenderOptions = {}): string {
  const tiny = typeof size === "number" && size <= 24;
  const dimension = typeof size === "number" ? `${size}` : escapeAttr(size);
  const extra = Object.entries(attributes)
    .filter(([name]) => /^[a-z][a-z0-9-]*$/.test(name))
    .map(([name, value]) => ` ${name}="${escapeAttr(value)}"`)
    .join("");
  const a11y = label ? `role="img" aria-label="${escapeAttr(label)}"` : `aria-hidden="true"`;
  const eyes = EYES.map(
    (e, i) =>
      `<g class="nestor-eye nestor-eye-${i === 0 ? "l" : "r"}">` +
      `<ellipse class="nestor-iris" cx="${e.cx}" cy="${e.cy}" rx="${EYE.rx}" ry="${EYE.ry}"/>` +
      `<rect class="nestor-lid" x="${e.cx - EYE.rx - 1}" y="${e.cy - EYE.ry - 1}" width="${EYE.rx * 2 + 2}" height="${EYE.ry * 2 + 2}"/>` +
      `</g>`,
  ).join("");
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${VIEWBOX}" width="${dimension}" height="${dimension}"`,
    ` class="nestor${tiny ? " nestor--tiny" : ""}${className ? ` ${escapeAttr(className)}` : ""}"`,
    ` data-state="${state}"${id ? ` id="${escapeAttr(id)}"` : ""}${extra} ${a11y}>`,
    ground ? `<ellipse class="nestor-ground" cx="60" cy="111" rx="28" ry="3.6"/>` : "",
    `<g class="nestor-figure"><g class="nestor-breath">`,
    `<path class="nestor-tuft" d="${TUFT}"/>`,
    `<path class="nestor-skin" d="${BODY}"/>`,
    tiny ? "" : `<g class="nestor-bow" ${bowPlacement()}>${bowShapes("nestor-bow-wing", "nestor-bow-knot")}</g>`,
    `<g class="nestor-face">`,
    `<g class="nestor-brows"><path class="nestor-brow nestor-brow-l" d="${brow(EYES[0].cx, EYES[0].cy)}"/>`,
    `<path class="nestor-brow nestor-brow-r" d="${brow(EYES[1].cx, EYES[1].cy)}"/></g>`,
    `<g class="nestor-eyes">${eyes}`,
    `<g class="nestor-happy">${EYES.map((e) => `<path d="${happyEye(e.cx, e.cy)}"/>`).join("")}</g>`,
    `<g class="nestor-shut">${EYES.map((e) => `<path d="${shutEye(e.cx, e.cy)}"/>`).join("")}</g>`,
    `</g>`,
    `<rect class="nestor-mouth" x="${MOUTH.x}" y="${MOUTH.y}" width="${MOUTH.width}" height="${MOUTH.height}"/>`,
    `</g></g></g>`,
    tiny
      ? ""
      : `<g class="nestor-signs">` +
        `<g class="nestor-thoughts">${THOUGHTS.map((d) => `<rect x="${d.x}" y="${d.y}" width="${d.size}" height="${d.size}"/>`).join("")}</g>` +
        `<path class="nestor-spinner" d="${SPINNER}"/>` +
        `<path class="nestor-sound" d="${SOUND}"/>` +
        `</g>`,
    `</svg>`,
  ].join("");
}

export interface Palette {
  ink: string;
  paper: string;
  ember: string;
}

export const PALETTES = {
  light: { ink: "#1d1913", paper: "#f5f0e6", ember: "#ad401d" },
  dark: { ink: "#eee7da", paper: "#16130f", ember: "#e8835c" },
} as const satisfies Record<string, Palette>;

/**
 * A still picture with its colours written in, for places without CSS: favicons, avatars,
 * sharing images. `background` draws a rounded tile behind it (an app-icon look).
 */
export function renderNestorStill(size: number, palette: Palette = PALETTES.light, background?: string): string {
  const tiny = size <= 24;
  const tile = background ? `<rect width="120" height="120" rx="26" fill="${background}"/>` : "";
  const scale = background ? `transform="translate(12 10) scale(0.8)"` : "";
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="${VIEWBOX}">`,
    `<title>Nestor</title>`,
    tile,
    `<g ${scale}>`,
    `<path d="${TUFT}" fill="${palette.ink}"/>`,
    `<path d="${BODY}" fill="${palette.ink}"/>`,
    tiny ? "" : `<g ${bowPlacement()}>${bowShapes(undefined, undefined, palette.paper, palette.ember)}</g>`,
    EYES.map((e) => `<ellipse cx="${e.cx}" cy="${e.cy}" rx="${EYE.rx}" ry="${EYE.ry}" fill="${palette.paper}"/>`).join(
      "",
    ),
    `<rect x="${MOUTH.x}" y="${MOUTH.y}" width="${MOUTH.width}" height="${MOUTH.height}" fill="${palette.ember}"/>`,
    `</g></svg>`,
  ].join("");
}

/* ── the bow tie, the logo and the monogram ─────────────────────────────────────────────── */

export interface BowTieOptions {
  /** width in pixels (or any CSS length); the height follows (24/44) */
  size?: number | string;
  className?: string;
  /** colours; by default the wings and knot follow `nestor.css` (ember in the logo) */
  wing?: string;
  knot?: string;
}

/** The bow tie alone, as SVG: the logo's mark, list markers, dividers. Decorative. */
export function renderBowTie({ size = 44, className = "", wing, knot }: BowTieOptions = {}): string {
  const width = typeof size === "number" ? `${size}` : escapeAttr(size);
  const height = typeof size === "number" ? ` height="${Math.round((size * 24) / 44)}"` : "";
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${BOW_VIEWBOX}" width="${width}"${height}` +
    ` class="nestor-tie${className ? ` ${escapeAttr(className)}` : ""}" aria-hidden="true">` +
    bowShapes("nestor-tie-wing", "nestor-tie-knot", wing, knot) +
    `</svg>`
  );
}

export type LogoVariant = "bow" | "cursor" | "lockup";

export interface LogoOptions {
  /**
   * `bow` (the default): "nestor" in the display serif, then the ember bow tie where the cursor was.
   * `cursor`: the original wordmark, with the ember block cursor. `lockup`: the character, then `bow`.
   */
  variant?: LogoVariant;
  /** the accessible name (the logo is a single image to assistive technology) */
  label?: string;
  className?: string;
}

/**
 * The logo as HTML (text in the page's display font, so it stays crisp and selectable-free):
 * size it with `font-size` on the element or a parent. Styles are in `nestor.css`.
 */
export function renderLogo({ variant = "bow", label = "Nestor", className = "" }: LogoOptions = {}): string {
  const mark =
    variant === "cursor"
      ? `<span class="nestor-logo-cursor"></span>`
      : `<span class="nestor-logo-tie">${renderBowTie({ size: "0.62em" })}</span>`;
  const character =
    variant === "lockup" ? `<span class="nestor-logo-character">${renderNestor({ size: "1.25em" })}</span>` : "";
  return (
    `<span class="nestor-logo nestor-logo--${variant}${className ? ` ${escapeAttr(className)}` : ""}" role="img" aria-label="${escapeAttr(label)}">` +
    `${character}<span class="nestor-logo-word" aria-hidden="true">nestor</span>${mark}</span>`
  );
}

/** The monogram: the bow tie on a rounded tile, for favicons, app icons and avatars. */
export function renderMarkStill(size: number, palette: Palette = PALETTES.light): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 64 64">` +
    `<title>Nestor</title><rect width="64" height="64" rx="14" fill="${palette.ink}"/>` +
    `<g transform="translate(32 33) scale(1.15)">${bowShapes(undefined, undefined, palette.paper, palette.ember)}</g></svg>`
  );
}
