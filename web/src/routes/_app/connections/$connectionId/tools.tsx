import { createFileRoute } from "@tanstack/react-router";
import { useConnection } from "@/features/connections/connection-detail";
import { ToolSettings } from "@/features/connections/tool-settings";
import { useCan } from "@/lib/session";

export const Route = createFileRoute("/_app/connections/$connectionId/tools")({ component: Page });

function Page() {
  const { connectionId } = Route.useParams();
  const connection = useConnection(connectionId);
  const editable = useCan("connections:write");
  if (!connection.data) return null;
  return <ToolSettings key={connection.data.id} editable={editable} connection={connection.data} />;
}
