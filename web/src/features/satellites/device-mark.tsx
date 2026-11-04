import type { LucideIcon } from "lucide-react";
import { Bot, Mic, MonitorSmartphone, RadioTower, ScanEye, Speaker } from "lucide-react";
import { BrandMark, brandOf, hasLogo } from "@/lib/brands";
import { cn } from "@/lib/utils";

/** What a device is, from what it can do: the body before the screen, the screen before the sound. */
const KINDS: [string[], LucideIcon][] = [
  [["motion.head", "expression.emotion"], Bot],
  [["text.display", "text.input"], MonitorSmartphone],
  [["audio.playback"], Speaker],
  [["audio.capture"], Mic],
  [["vision.person_detection"], ScanEye],
];

/**
 * A satellite's mark: its maker's logo when the maker has one, otherwise a picture of what the device
 * is (a robot, a screen, a speaker, a microphone, a sensor), never a letter in a box.
 */
export function DeviceMark({
  brand,
  capabilities,
  className,
}: {
  brand: string | null | undefined;
  capabilities: readonly string[];
  className?: string;
}) {
  const slug = brandOf(brand);
  if (slug && hasLogo(slug)) return <BrandMark brand={slug} className={className} />;
  const Icon = KINDS.find(([names]) => names.some((n) => capabilities.includes(n)))?.[1] ?? RadioTower;
  return <Icon className={cn("size-4 shrink-0", className)} aria-hidden="true" />;
}
