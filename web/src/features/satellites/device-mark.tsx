import { RadioTower } from "lucide-react";
import { BrandMark, brandOf, hasLogo } from "@/lib/brands";
import { DEVICE_KIND } from "@/lib/icons";
import { cn } from "@/lib/utils";

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
  capabilities: readonly { name: string }[];
  className?: string;
}) {
  const slug = brandOf(brand);
  if (slug && hasLogo(slug)) return <BrandMark brand={slug} className={className} />;
  const names = capabilities.map((c) => c.name);
  const Icon = DEVICE_KIND.find(([kind]) => kind.some((n) => names.includes(n)))?.[1] ?? RadioTower;
  return <Icon className={cn("size-4 shrink-0", className)} aria-hidden="true" />;
}
