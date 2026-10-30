import { createFileRoute, Outlet } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { SatelliteFrame } from "@/features/satellites/satellite-detail";

export const Route = createFileRoute("/_app/satellites/$satelliteId")({ component: Layout });

function Layout() {
  const { satelliteId } = Route.useParams();
  return (
    <Guard scope="satellites:read">
      <SatelliteFrame id={satelliteId}>
        <Outlet />
      </SatelliteFrame>
    </Guard>
  );
}
