import type { ReactNode } from "react";
import { PageHeader } from "@/components/page";
import { useT } from "@/i18n";
import { type Permission, useCan } from "@/lib/session";

/** A whole screen the account may not see: explained, not hidden behind a blank page. */
export function Guard({ scope, children }: { scope: Permission; children: ReactNode }) {
  const t = useT();
  if (useCan(scope)) return children;
  return <PageHeader title={t("forbidden-title")}>{t("forbidden-text")}</PageHeader>;
}
