import type * as React from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * A time of day (`HH:MM`), as shadcn builds it: the browser's time field in the admin's input, without its picker
 * icon (each part is typed or stepped with the arrow keys).
 */
function TimeInput({ className, ...props }: Omit<React.ComponentProps<typeof Input>, "type">) {
  return (
    <Input
      type="time"
      step={60}
      data-slot="time-input"
      className={cn(
        "w-28 appearance-none tabular-nums [&::-webkit-calendar-picker-indicator]:hidden [&::-webkit-calendar-picker-indicator]:appearance-none",
        className,
      )}
      {...props}
    />
  );
}

export { TimeInput };
