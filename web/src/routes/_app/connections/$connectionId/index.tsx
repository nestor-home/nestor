import { createFileRoute } from "@tanstack/react-router";
import { ConnectionOverview, useConnection } from "@/features/connections/connection-detail";

export const Route = createFileRoute("/_app/connections/$connectionId/")({ component: Page });

function Page() {
  const { connectionId } = Route.useParams();
  const connection = useConnection(connectionId);
  if (!connection.data) return null;
  return <ConnectionOverview connection={connection.data} />;
}
