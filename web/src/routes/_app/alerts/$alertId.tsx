import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { AlertDetail } from "@/features/alerts/alerts";

export const Route = createFileRoute("/_app/alerts/$alertId")({ component: Page });

function Page() {
  const { alertId } = Route.useParams();
  return (
    <Guard scope="alerts:read">
      <AlertDetail id={alertId} />
    </Guard>
  );
}
