import { RadioTower } from "lucide-react";
import { BrandMark, brandOf, hasLogo } from "@/lib/brands";
import { CAPABILITY_ICON, DEVICE_KIND } from "@/lib/icons";
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

/** The device's mark on its tile: what leads a card or a page that stands for a satellite. */
export function DeviceTile({
  brand,
  capabilities,
  className,
}: {
  brand: string | null | undefined;
  capabilities: readonly { name: string }[];
  className?: string;
}) {
  return (
    <span className={cn("grid size-11 shrink-0 place-items-center rounded-xl bg-paper-sunken text-ink", className)}>
      <DeviceMark brand={brand} capabilities={capabilities} className="size-[45%]" />
    </span>
  );
}

/** What a device can do, as small marks named for who cannot see them. */
export function CapabilityMarks({
  capabilities,
  className,
}: {
  capabilities: readonly { name: string; label: string }[];
  className?: string;
}) {
  return (
    <span className={cn("flex flex-wrap gap-2 text-ink-muted", className)}>
      {capabilities.map((c) => {
        const Icon = CAPABILITY_ICON[c.name];
        return Icon ? (
          <span key={c.name} title={c.label}>
            <Icon className="size-4" aria-label={c.label} />
          </span>
        ) : null;
      })}
    </span>
  );
}
