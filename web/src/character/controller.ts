/**
 * Brings a rendered Nestor to life: where it looks, how it leans, when it blinks, what it says.
 * Framework-agnostic (a DOM element in, a small typed API out). It animates with one
 * requestAnimationFrame loop that runs only while the character is on screen and the tab is
 * visible, writes only CSS custom properties (transform/opacity happen in nestor.css), and under
 * `prefers-reduced-motion` holds a static pose: no loop, no blink, gaze set without easing.
 */
import type { NestorState } from "./render";

export interface ControllerOptions {
  /** an element that shows what it says (its text is replaced, `data-open` toggled) */
  bubble?: HTMLElement | null;
  /** blinks on its own, every few seconds */
  autoBlink?: boolean;
  /** small eye movements of its own when nothing holds its attention */
  saccades?: boolean;
  /** force reduced motion (tests); defaults to the user's preference */
  reducedMotion?: boolean;
}

export interface Gaze {
  gx: number;
  gy: number;
  turn: number;
  lean: number;
}

const LIMIT = { gx: 5, gy: 4.5, turn: 1, lean: 4 };

/**
 * The gaze toward a point, from the character's centre, both in viewport pixels. `reach` is the
 * distance at which it looks fully aside (by default, a third of the viewport's diagonal).
 */
export function gazeToward(target: { x: number; y: number }, centre: { x: number; y: number }, reach = 480): Gaze {
  const clamp = (v: number) => Math.max(-1, Math.min(1, v));
  const dx = clamp((target.x - centre.x) / reach);
  const dy = clamp((target.y - centre.y) / reach);
  return {
    gx: dx * LIMIT.gx,
    gy: dy * LIMIT.gy,
    turn: dx * 0.6 * LIMIT.turn,
    lean: dx * LIMIT.lean * 0.6 + (dy > 0.6 ? 1.2 : 0),
  };
}

/** One step of easing toward the target: frame-rate independent (dt in ms). */
export function ease(current: number, target: number, dt: number, halfLife = 90): number {
  return target + (current - target) * 2 ** (-dt / halfLife);
}

/** How long a line stays on screen: enough to read it, not more. */
export function speakingTime(text: string): number {
  return Math.min(6000, 900 + text.length * 55);
}

export class NestorController {
  readonly element: SVGSVGElement;
  private readonly bubble: HTMLElement | null;
  private readonly reduced: boolean;
  private readonly options: ControllerOptions;
  private current: Gaze = { gx: 0, gy: 0, turn: 0, lean: 0 };
  private target: Gaze = { gx: 0, gy: 0, turn: 0, lean: 0 };
  /** where it means to look; saccades wander around it */
  private aim: Gaze = { gx: 0, gy: 0, turn: 0, lean: 0 };
  private frame = 0;
  private last = 0;
  private visible = true;
  private blinkTimer = 0;
  private saccadeTimer = 0;
  private sayTimer = 0;
  private held = 0;
  private readonly observer: IntersectionObserver | null;
  private readonly onVisibility = () => this.sync();

  constructor(element: SVGSVGElement, options: ControllerOptions = {}) {
    this.element = element;
    this.options = options;
    this.bubble = options.bubble ?? null;
    this.reduced =
      options.reducedMotion ??
      (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
    element.dataset.live = "";
    if (typeof IntersectionObserver === "function") {
      this.observer = new IntersectionObserver(([entry]) => {
        this.visible = Boolean(entry?.isIntersecting);
        this.sync();
      });
      this.observer.observe(element);
    } else {
      this.observer = null;
    }
    document.addEventListener("visibilitychange", this.onVisibility);
    this.sync();
  }

  get state(): NestorState {
    return (this.element.dataset.state as NestorState) ?? "idle";
  }

  set state(state: NestorState) {
    this.element.dataset.state = state;
  }

  setState(state: NestorState): this {
    this.state = state;
    return this;
  }

  /** Looks toward a point of the viewport, or an element's centre. */
  lookAt(xOrElement: number | Element, y?: number): this {
    const point =
      typeof xOrElement === "number"
        ? { x: xOrElement, y: y ?? 0 }
        : (() => {
            const box = xOrElement.getBoundingClientRect();
            return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
          })();
    const box = this.element.getBoundingClientRect();
    const reach = Math.hypot(innerWidth, innerHeight) / 3;
    this.target = gazeToward(point, { x: box.left + box.width / 2, y: box.top + box.height * 0.55 }, reach);
    this.aim = { ...this.target };
    this.held = performance.now();
    if (this.reduced) this.snap();
    return this;
  }

  /** Back to looking ahead. */
  center(): this {
    this.target = { gx: 0, gy: 0, turn: 0, lean: 0 };
    this.aim = { ...this.target };
    if (this.reduced) this.snap();
    return this;
  }

  /** A tilt of the head (degrees), as when it is curious. */
  lean(degrees: number): this {
    this.target = { ...this.target, lean: Math.max(-8, Math.min(8, degrees)) };
    this.aim = { ...this.aim, lean: this.target.lean };
    return this;
  }

  blink(): this {
    if (this.reduced) return this;
    this.element.classList.add("nestor-blink");
    window.setTimeout(() => this.element.classList.remove("nestor-blink"), 130);
    return this;
  }

  /** A one-off gesture: a small hop (`bob`) or a butler's bow (`greet`). */
  gesture(name: "bob" | "greet"): this {
    if (this.reduced) return this;
    const className = `nestor-${name}`;
    this.element.classList.remove(className);
    void this.element.getBoundingClientRect();
    this.element.classList.add(className);
    window.setTimeout(() => this.element.classList.remove(className), 1500);
    return this;
  }

  /**
   * Says a line: the bubble shows it, the mouth speaks for as long as it takes to read, then it
   * returns to `after` (idle by default). Resolves when it is done.
   */
  say(text: string, after: NestorState = "idle"): Promise<void> {
    clearTimeout(this.sayTimer);
    if (this.bubble) {
      this.bubble.textContent = text;
      this.bubble.dataset.open = "";
    }
    this.state = "speaking";
    return new Promise((resolve) => {
      this.sayTimer = window.setTimeout(() => {
        if (this.bubble) delete this.bubble.dataset.open;
        if (this.state === "speaking") this.state = after;
        resolve();
      }, speakingTime(text));
    });
  }

  /** Whether the animation loop is running (for tests and debugging). */
  get running(): boolean {
    return this.frame !== 0;
  }

  destroy(): void {
    this.stop();
    clearTimeout(this.sayTimer);
    this.observer?.disconnect();
    document.removeEventListener("visibilitychange", this.onVisibility);
    delete this.element.dataset.live;
    delete this.element.dataset.running;
  }

  private sync(): void {
    const active = this.visible && !document.hidden && !this.reduced;
    if (active && !this.frame) this.start();
    if (!active && this.frame) this.stop();
  }

  private start(): void {
    this.last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(64, now - this.last);
      this.last = now;
      this.current = {
        gx: ease(this.current.gx, this.target.gx, dt),
        gy: ease(this.current.gy, this.target.gy, dt),
        turn: ease(this.current.turn, this.target.turn, dt, 160),
        lean: ease(this.current.lean, this.target.lean, dt, 220),
      };
      this.apply(this.current);
      this.frame = requestAnimationFrame(tick);
    };
    this.frame = requestAnimationFrame(tick);
    this.element.dataset.running = "true";
    if (this.options.autoBlink !== false) this.scheduleBlink();
    if (this.options.saccades) this.scheduleSaccade();
  }

  private stop(): void {
    cancelAnimationFrame(this.frame);
    this.frame = 0;
    clearTimeout(this.blinkTimer);
    clearTimeout(this.saccadeTimer);
    this.element.dataset.running = "false";
  }

  /** jumps to the target without easing (reduced motion) */
  private snap(): void {
    this.current = { ...this.target };
    this.apply(this.current);
  }

  private apply(g: Gaze): void {
    const style = this.element.style;
    style.setProperty("--nestor-gx", g.gx.toFixed(2));
    style.setProperty("--nestor-gy", g.gy.toFixed(2));
    style.setProperty("--nestor-turn", g.turn.toFixed(3));
    style.setProperty("--nestor-lean", g.lean.toFixed(2));
  }

  private scheduleBlink(): void {
    this.blinkTimer = window.setTimeout(
      () => {
        this.blink();
        if (Math.random() < 0.18) window.setTimeout(() => this.blink(), 220);
        this.scheduleBlink();
      },
      2200 + Math.random() * 4200,
    );
  }

  private scheduleSaccade(): void {
    this.saccadeTimer = window.setTimeout(
      () => {
        // only when nothing has held its attention for a while
        if (performance.now() - this.held > 2500 && this.state !== "thinking") {
          this.target = {
            ...this.aim,
            gx: Math.max(-LIMIT.gx, Math.min(LIMIT.gx, this.aim.gx + (Math.random() - 0.5) * 2.4)),
            gy: Math.max(-LIMIT.gy, Math.min(LIMIT.gy, this.aim.gy + (Math.random() - 0.5) * 1.6)),
          };
        }
        this.scheduleSaccade();
      },
      1600 + Math.random() * 2600,
    );
  }
}
