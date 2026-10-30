/** The agent's bow tie (the character module's own), as a discreet mark. Decorative. */
import { renderBowTie } from "@/character";
import "@/character/nestor.css";

export function BowTie({ size = 22, className }: { size?: number; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={className}
      style={{ display: "inline-flex", lineHeight: 0 }}
      // biome-ignore lint/security/noDangerouslySetInnerHtml: the character module's own markup, from constant shapes
      dangerouslySetInnerHTML={{ __html: renderBowTie({ size }) }}
    />
  );
}
