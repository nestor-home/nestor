import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { SystemView } from "@/features/system/system-view";

export const Route = createFileRoute("/_app/system")({ component: System });

function System() {
  return (
    <Guard scope="satellites:read">
      <SystemView />
    </Guard>
  );
}
