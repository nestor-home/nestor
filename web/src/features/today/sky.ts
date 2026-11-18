/** The sky of the hour, as the film paints it: four lights, and where the sun or the moon stands. */
export type Phase = "night" | "dawn" | "day" | "dusk";

const hourOf = (d: Date) => d.getHours() + d.getMinutes() / 60;

export function phaseOf(date: Date): Phase {
  const h = hourOf(date);
  if (h < 5.5 || h >= 21.5) return "night";
  if (h < 8) return "dawn";
  if (h < 17.5) return "day";
  return "dusk";
}

/** Where the light stands in the sky, in percent of its box: the sun on its arc, the moon in its corner. */
export function orbOf(date: Date): { left: string; top: string } {
  if (phaseOf(date) === "night") return { left: "12%", top: "20%" };
  const p = Math.min(1, Math.max(0, (hourOf(date) - 5.5) / 16));
  return { left: `${6 + p * 88}%`, top: `${62 - Math.sin(Math.PI * p) * 46}%` };
}
