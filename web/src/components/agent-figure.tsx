/**
 * The agent's figure, wherever the agent appears (sidebar, home, sign-in, empty and loading states,
 * restart). STAND-IN: the canonical character is being designed as a shared module
 * (`src/character/`, SVG + controller + React wrapper). This component keeps that module's props
 * (`state`, `size`, `lookAt`, `label`) so swapping it is a one-file change; it draws only a neutral
 * face whose eyes and mouth follow the state.
 */
import { cn } from "@/lib/utils";

export type FigureState =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "laughing"
  | "sleeping"
  | "working"
  | "concerned";

export type FigureSize = "xs" | "sm" | "md" | "lg" | "hero";

const PX: Record<FigureSize, number> = { xs: 16, sm: 24, md: 40, lg: 96, hero: 168 };

export interface FigureProps {
  state: FigureState;
  size?: FigureSize;
  /** Where it looks, each axis in [-1, 1] (0, 0 straight ahead). */
  lookAt?: { x: number; y: number };
  /** Its accessible name; without one the figure is decoration. */
  label?: string;
  className?: string;
}

export function AgentFigure({ state, size = "md", lookAt, label, className }: FigureProps) {
  const px = PX[size];
  const gaze = {
    x: Math.max(-1, Math.min(1, lookAt?.x ?? 0)) * 4,
    y: Math.max(-1, Math.min(1, lookAt?.y ?? (state === "thinking" ? -0.8 : state === "working" ? 0.6 : 0))) * 3,
  };
  const a11y = label ? { role: "img", "aria-label": label } : { "aria-hidden": true as const };
  const asleep = state === "sleeping";
  return (
    // biome-ignore lint/a11y/noSvgWithoutTitle: titled when labelled, hidden from assistive tech otherwise
    <svg
      viewBox="0 0 48 48"
      width={px}
      height={px}
      data-state={state}
      className={cn("shrink-0 overflow-visible", className)}
      {...a11y}
    >
      {label ? <title>{label}</title> : null}
      <circle cx="24" cy="24" r="21" className="fill-paper-raised stroke-ink" strokeWidth={size === "xs" ? 3 : 1.6} />
      {size === "xs" ? null : (
        <g className="transition-transform duration-500" style={{ transform: `translate(${gaze.x}px, ${gaze.y}px)` }}>
          {asleep ? (
            <>
              <path d="M14 22 q3 2 6 0" className="fill-none stroke-ink" strokeWidth="1.6" strokeLinecap="round" />
              <path d="M28 22 q3 2 6 0" className="fill-none stroke-ink" strokeWidth="1.6" strokeLinecap="round" />
            </>
          ) : (
            <>
              <circle cx="17" cy="21" r={state === "listening" ? 2.6 : 2.1} className="fill-ink" />
              <circle cx="31" cy="21" r={state === "listening" ? 2.6 : 2.1} className="fill-ink" />
            </>
          )}
          {state === "concerned" ? (
            <>
              <path d="M13 15 l7 2" className="stroke-ink" strokeWidth="1.4" strokeLinecap="round" />
              <path d="M35 15 l-7 2" className="stroke-ink" strokeWidth="1.4" strokeLinecap="round" />
            </>
          ) : null}
          <Mouth state={state} />
        </g>
      )}
      {state === "working" || state === "thinking" ? (
        <circle
          cx="24"
          cy="24"
          r="23.5"
          className="mind-turn-fast fill-none stroke-ember [transform-origin:24px_24px]"
          strokeWidth="1.2"
          strokeDasharray="10 140"
          strokeLinecap="round"
        />
      ) : null}
    </svg>
  );
}

function Mouth({ state }: { state: FigureState }) {
  const common = { className: "fill-none stroke-ink", strokeWidth: 1.6, strokeLinecap: "round" as const };
  switch (state) {
    case "speaking":
      return (
        <ellipse cx="24" cy="31" rx="3.2" ry="2.4" className="mind-breathe fill-ink [transform-origin:24px_31px]" />
      );
    case "laughing":
      return <path d="M17 29 q7 7 14 0 z" className="fill-ink" />;
    case "concerned":
      return <path d="M19 33 q5 -3 10 0" {...common} />;
    case "sleeping":
      return <path d="M21 31 h6" {...common} />;
    case "listening":
      return <path d="M20 31 q4 2 8 0" {...common} />;
    default:
      return <path d="M19 30 q5 3 10 0" {...common} />;
  }
}
