import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "group/button inline-flex shrink-0 pointer-coarse:min-h-11 pointer-coarse:min-w-11 items-center justify-center gap-1.5 rounded-md border text-sm font-medium whitespace-nowrap transition-[color,background-color,border-color] duration-(--duration) outline-none select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ember active:not-disabled:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 data-disabled:pointer-events-none data-disabled:opacity-50 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "border-ink bg-ink text-paper hover:bg-ink/85",
        accent: "border-ember bg-ember text-on-ember hover:bg-ember/90",
        outline:
          "border-rule-strong bg-paper-raised text-ink hover:border-ink aria-expanded:border-ink data-popup-open:border-ink",
        secondary: "border-transparent bg-paper-sunken text-ink hover:bg-rule",
        ghost: "border-transparent text-ink-muted hover:bg-paper-sunken hover:text-ink aria-expanded:bg-paper-sunken",
        destructive: "border-brick/40 bg-transparent text-brick hover:border-brick hover:bg-brick-soft",
        link: "border-transparent text-ember underline-offset-4 hover:underline",
      },
      size: {
        default: "h-8 px-3",
        xs: "h-6 gap-1 px-2 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 px-2.5 text-[0.8rem] [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-10 px-4",
        icon: "size-8",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7",
        "icon-lg": "size-9",
      },
    },
    compoundVariants: [{ variant: "link", class: "h-auto px-0" }],
    defaultVariants: { variant: "default", size: "default" },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return <ButtonPrimitive data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
