import { createFileRoute } from "@tanstack/react-router";
import { SatelliteActivity, useSatellite } from "@/features/satellites/satellite-detail";

export const Route = createFileRoute("/_app/satellites/$satelliteId/activity")({ component: Page });

function Page() {
  const { satelliteId } = Route.useParams();
  const { satellite } = useSatellite(satelliteId);
  return satellite ? <SatelliteActivity satellite={satellite} /> : null;
}
