import { cn } from "@/lib/utils";

/** One choice among a few, as pills in a row that scrolls on a phone: the lanes of a list, each with its count. */
export function Chips<T extends string>({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: readonly { id: T; label: string; count?: number }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <fieldset className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
      <legend className="sr-only">{label}</legend>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          aria-pressed={value === item.id}
          onClick={() => onChange(item.id)}
          className={cn(
            "inline-flex h-10 shrink-0 items-center gap-2 rounded-full px-4 text-[0.95rem] font-medium transition-colors",
            value === item.id ? "bg-ink text-paper" : "bg-paper-raised text-ink-muted shadow-(--lift) hover:text-ink",
          )}
        >
          {item.label}
          {item.count ? (
            <span className={cn("text-[0.8rem] tabular", value === item.id ? "text-paper/70" : "text-ink-faint")}>
              {item.count}
            </span>
          ) : null}
        </button>
      ))}
    </fieldset>
  );
}
