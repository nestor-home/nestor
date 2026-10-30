import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

export interface ChoiceOption<T extends string> {
  value: T;
  label: string;
  hint?: string;
}

/** shadcn's Select for a short fixed list, labelled by `id` (a `<label htmlFor>` elsewhere). */
export function Choice<T extends string>({
  id,
  value,
  options,
  onChange,
  disabled,
  className,
  size = "default",
  describedBy,
}: {
  id: string;
  value: T;
  options: ChoiceOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
  size?: "sm" | "default";
  describedBy?: string;
}) {
  return (
    <Select
      value={value}
      onValueChange={(next) => next !== null && onChange(next as T)}
      disabled={disabled}
      items={options.map((o) => ({ value: o.value, label: o.label }))}
    >
      <SelectTrigger
        id={id}
        size={size}
        className={cn("w-full bg-paper-raised", className)}
        aria-describedby={describedBy}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false}>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
