import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { ConnectionsView } from "@/features/connections/connections-view";

export const Route = createFileRoute("/_app/connections/")({ component: Connections });

function Connections() {
  return (
    <Guard scope="connections:read">
      <ConnectionsView />
    </Guard>
  );
}
