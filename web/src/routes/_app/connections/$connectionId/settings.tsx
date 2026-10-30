import { createFileRoute } from "@tanstack/react-router";
import { ConnectionSettings, useConnection } from "@/features/connections/connection-detail";

export const Route = createFileRoute("/_app/connections/$connectionId/settings")({ component: Page });

function Page() {
  const { connectionId } = Route.useParams();
  const connection = useConnection(connectionId);
  if (!connection.data) return null;
  return <ConnectionSettings connection={connection.data} />;
}
