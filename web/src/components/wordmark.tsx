import { renderLogo } from "@/character";
import "@/character/nestor.css";
import { cn } from "@/lib/utils";

/**
 * The logo: "nestor" in the display serif with the ember bow tie (`renderLogo({variant: "bow"})`
 * from the character module), sized by the font size it is given.
 */
export function Wordmark({ className }: { className?: string; compact?: boolean }) {
  return (
    <span
      className={cn("inline-flex leading-none text-ink", className)}
      // biome-ignore lint/security/noDangerouslySetInnerHtml: the character module's own markup, from constant shapes and escaped attributes
      dangerouslySetInnerHTML={{ __html: renderLogo({ variant: "bow" }) }}
    />
  );
}
