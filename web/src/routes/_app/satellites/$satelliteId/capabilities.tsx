import { createFileRoute } from "@tanstack/react-router";
import { SatelliteCapabilities, useSatellite } from "@/features/satellites/satellite-detail";

export const Route = createFileRoute("/_app/satellites/$satelliteId/capabilities")({ component: Page });

function Page() {
  const { satelliteId } = Route.useParams();
  const { satellite } = useSatellite(satelliteId);
  return satellite ? <SatelliteCapabilities satellite={satellite} /> : null;
}
