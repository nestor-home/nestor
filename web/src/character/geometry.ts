/**
 * Nestor's drawing, as data: the one source of its shapes for every surface (the admin, the
 * website, icons). Units are those of a 120 × 120 box; the character stands on y = 108.
 *
 * Its marks: a pebble that leans slightly right, a quiff swept to the right, two paper eyes,
 * the ember cursor of the wordmark as its mouth (its voice), and a small bow tie: the butler at
 * your service, without the costume. Flat colours only: nothing else on its skin.
 */
export const VIEWBOX = "0 0 120 120";
export const SIZE = 120;

export const BODY = "M57 21C80 19 100 37 102 63C104 90 87 107 61 107C35 107 17 93 17 66C17 41 34 23 57 21Z";
/** The quiff: perks up when it listens, droops when it sleeps. Rotates around its root. */
export const TUFT = "M50 23C49 16 53 10 60 6C59 11 61 15 66 20C61 21 55 22 50 23Z";
export const TUFT_ROOT = { x: 56, y: 22 };
/**
 * The bow tie, drawn around its knot at (0, 0) in a 44 × 24 box: the same one in the logo, the
 * monogram and on the character (placed with BOW_AT).
 */
export const BOW_WINGS = [
  "M-2.4 -2.4C-6 -4.6 -11 -8.6 -16.5 -10.2C-19.6 -11 -21 -6 -21 0C-21 6 -19.6 11 -16.5 10.2C-11 8.6 -6 4.6 -2.4 2.4Z",
  "M2.4 -2.4C6 -4.6 11 -8.6 16.5 -10.2C19.6 -11 21 -6 21 0C21 6 19.6 11 16.5 10.2C11 8.6 6 4.6 2.4 2.4Z",
] as const;
export const BOW_KNOT = { x: -3.4, y: -4.4, width: 6.8, height: 8.8, r: 2 };
export const BOW_VIEWBOX = "-22 -12 44 24";
/** Where the bow tie sits on the character: centred at the foot of its body. */
export const BOW_AT = { x: 59.5, y: 100.5, scale: 0.44 };

export const EYES = [
  { cx: 46.5, cy: 61 },
  { cx: 72.5, cy: 61 },
] as const;
export const EYE = { rx: 6.4, ry: 8.4 };
/** The ember cursor, as a mouth. */
export const MOUTH = { x: 55.5, y: 77, width: 8, height: 4.5 };
/** Where its body turns around (the floor, under its centre). */
export const ORIGIN = { x: 60, y: 108 };

/** Laughing and sleeping eyes, drawn around each eye's centre. */
export const happyEye = (cx: number, cy: number) => `M${cx - 6} ${cy + 3}Q${cx} ${cy - 7} ${cx + 6} ${cy + 3}`;
export const shutEye = (cx: number, cy: number) => `M${cx - 6} ${cy + 1}Q${cx} ${cy + 5} ${cx + 6} ${cy + 1}`;
/** A short brow above an eye. */
export const brow = (cx: number, cy: number) => `M${cx - 5} ${cy - 14}L${cx + 5} ${cy - 14}`;

/** Thinking: three squares rising to its upper right. Working: a quarter turn spinning there. */
export const THOUGHTS = [
  { x: 97, y: 26, size: 4 },
  { x: 104, y: 18, size: 5 },
  { x: 111, y: 9, size: 6 },
] as const;
export const SPINNER = "M104 20A10 10 0 0 1 114 30";
/** Listening: one thin arc of sound at its side (with the quiff raised). */
export const SOUND = "M109 50Q115 61 109 72";
