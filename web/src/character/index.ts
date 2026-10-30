/**
 * Nestor, the character: the agent's one digital identity, on every surface (the admin, the
 * website, icons). Physical bodies (a Reachy Mini, a speaker…) are bodies it takes; this is who
 * it is.
 *
 *   import "./nestor.css";                       // once, wherever it is shown
 *   el.innerHTML = renderNestor({ state: "idle", size: 120, label: "Nestor" });
 *   const nestor = new NestorController(el.querySelector("svg")!, { bubble, saccades: true });
 *   nestor.lookAt(event.clientX, event.clientY); nestor.say("On it."); nestor.state = "thinking";
 *
 * The logo: `renderLogo()` ("nestor" and the ember bow tie, sized by font-size), the bow tie alone:
 * `renderBowTie()`, the monogram for icons: `renderMarkStill()`.
 *
 * React: `import { Nestor } from "./react"`. Stills with written colours (favicons, avatars,
 * sharing images): `renderNestorStill(size, PALETTES.light)`.
 *
 * The canonical source lives in nestor/web/src/character/; nestor-web keeps a verbatim copy
 * and a test fails when they drift.
 */
export { type ControllerOptions, ease, type Gaze, gazeToward, NestorController, speakingTime } from "./controller";
export * as geometry from "./geometry";
export {
  type BowTieOptions,
  type LogoOptions,
  type LogoVariant,
  type NestorState,
  PALETTES,
  type Palette,
  type RenderOptions,
  renderBowTie,
  renderLogo,
  renderMarkStill,
  renderNestor,
  renderNestorStill,
  STATES,
} from "./render";
