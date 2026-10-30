import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { WatchesList } from "@/features/watches/watches";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/watches/")({ component: Watches });

function Watches() {
  const t = useT();
  return (
    <Guard scope="watches:read">
      <PageHeader title={t("watch-title")} />
      <WatchesList />
    </Guard>
  );
}
