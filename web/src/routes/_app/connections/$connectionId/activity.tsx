import { createFileRoute } from "@tanstack/react-router";
import { ActivityList } from "@/features/journal/activity-list";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/connections/$connectionId/activity")({ component: Page });

function Page() {
  const { connectionId } = Route.useParams();
  const t = useT();
  return (
    <ActivityList
      filters={{ connection: connectionId }}
      search={{ connection: connectionId }}
      limit={20}
      empty={t("conn-no-activity")}
    />
  );
}
