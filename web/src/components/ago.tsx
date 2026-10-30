import { useEffect, useState } from "react";
import { moment } from "@/lib/dates";
import { ago } from "@/lib/time";
import { cn } from "@/lib/utils";

/** `il y a 3 min`, kept fresh, with the exact time on hover and for machines. */
export function Ago({ iso, className }: { iso: string; className?: string }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(timer);
  }, []);
  return (
    <time dateTime={iso} title={moment(iso, now)} className={cn("tabular", className)}>
      {ago(iso, now)}
    </time>
  );
}
