import type { Crumb } from "@/components/crumbs";
import { tr } from "@/i18n/runtime";

/** Where a connections screen sits: under Settings, then under Connections when it is deeper. */
export function trail(...deeper: string[]): Crumb[] {
  return [
    { label: tr("space-settings"), link: { to: "/settings" } },
    { label: tr("conn-title"), link: { to: "/connections" } },
    ...deeper.map((label) => ({ label })),
  ];
}
