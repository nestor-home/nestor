/**
 * The agent's figure wherever it appears in the admin: the shared character (`@/character`),
 * at the admin's sizes. `live` brings it to life (blinks, gaze, the controller in `onReady`).
 */
import type { ControllerOptions, NestorController } from "@/character";
import { Nestor } from "@/character/react";
import type { NestorState } from "@/character/render";

export type FigureState = NestorState;
export type FigureSize = "xs" | "sm" | "md" | "lg" | "hero";

const PX: Record<FigureSize, number> = { xs: 16, sm: 28, md: 44, lg: 120, hero: 220 };

export interface FigureProps {
  state: FigureState;
  size?: FigureSize;
  /** its accessible name; without one it is decoration */
  label?: string;
  className?: string;
  live?: boolean | ControllerOptions;
  ground?: boolean;
  onReady?: (controller: NestorController) => void;
}

export function AgentFigure({ state, size = "md", label, className, live, ground, onReady }: FigureProps) {
  return (
    <Nestor
      state={state}
      size={PX[size]}
      label={label}
      className={className}
      live={live}
      ground={ground}
      onReady={onReady}
    />
  );
}
