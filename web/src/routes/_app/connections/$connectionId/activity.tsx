import { createFileRoute } from "@tanstack/react-router";
import { ConnectionActivity } from "@/features/connections/connection-view";

export const Route = createFileRoute("/_app/connections/$connectionId/activity")({ component: Page });

function Page() {
  const { connectionId } = Route.useParams();
  return <ConnectionActivity id={connectionId} />;
}
