import { useMemo } from "react";
import { encode } from "uqr";
import { cn } from "@/lib/utils";

/**
 * A QR code drawn here, from the text alone (`uqr`, no network, no canvas): one path of dark
 * modules on a light quiet zone, so a camera reads it in either theme.
 */
export function QrCode({ value, label, className }: { value: string; label: string; className?: string }) {
  const { size, path } = useMemo(() => {
    const qr = encode(value, { ecc: "M", border: 2 });
    let d = "";
    qr.data.forEach((row, y) => {
      row.forEach((dark, x) => {
        if (dark) d += `M${x} ${y}h1v1h-1z`;
      });
    });
    return { size: qr.size, path: d };
  }, [value]);
  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={label}
      shapeRendering="crispEdges"
      className={cn("rounded-md bg-white", className)}
    >
      <title>{label}</title>
      <path d={path} fill="#1d1913" />
    </svg>
  );
}
