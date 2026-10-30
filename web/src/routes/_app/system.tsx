import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { SystemView } from "@/features/system/system-view";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/system")({ component: System });

function System() {
  const t = useT();
  return (
    <Guard scope="satellites:read">
      <PageHeader title={t("sys-title")} />
      <SystemView />
    </Guard>
  );
}
