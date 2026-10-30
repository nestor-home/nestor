import type { ReactNode } from "react";
import type { Scope } from "@/api";
import { useT } from "@/i18n";
import { useCan } from "@/lib/session";

/** A whole screen the account may not see: explained, not hidden behind a blank page. */
export function Guard({ scope, children }: { scope: Scope; children: ReactNode }) {
  const t = useT();
  if (useCan(scope)) return children;
  return (
    <div className="max-w-lg pt-10">
      <h1 className="text-3xl font-normal">{t("forbidden-title")}</h1>
      <p className="mt-3 text-ink-muted">{t("forbidden-text")}</p>
    </div>
  );
}
