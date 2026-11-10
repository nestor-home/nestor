import type { Risk } from "@/api";
import { Tag } from "@/components/status";
import { riskLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

const RISK_TONE: Record<Risk, string> = {
  read: "",
  write: "border-amber/50 text-amber",
  sensitive: "border-brick/50 text-brick",
};

/** A tool's risk as a chip, the same colour wherever a tool is listed. */
export function RiskTag({ risk }: { risk: Risk }) {
  return <Tag className={cn(RISK_TONE[risk])}>{riskLabel(risk)}</Tag>;
}
