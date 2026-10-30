import { CircleAlert, CircleCheck, Info, LoaderCircle, TriangleAlert } from "lucide-react";
import type { CSSProperties } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import { useTheme } from "@/lib/theme";

/** shadcn's Sonner, themed by Nestor's own theme instead of next-themes. */
const Toaster = (props: ToasterProps) => {
  const { resolved } = useTheme();
  return (
    <Sonner
      theme={resolved}
      className="toaster group"
      position="bottom-right"
      icons={{
        success: <CircleCheck className="size-4 text-sage" />,
        info: <Info className="size-4" />,
        warning: <TriangleAlert className="size-4 text-amber" />,
        error: <CircleAlert className="size-4 text-brick" />,
        loading: <LoaderCircle className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--ink)",
          "--normal-text": "var(--paper)",
          "--normal-border": "var(--ink)",
          "--border-radius": "var(--radius)",
        } as CSSProperties
      }
      toastOptions={{ classNames: { toast: "font-sans text-sm" } }}
      {...props}
    />
  );
};

export { Toaster };
