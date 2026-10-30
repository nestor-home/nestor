import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { WatchDetail } from "@/features/watches/watches";

export const Route = createFileRoute("/_app/watches/$watchId")({ component: Page });

function Page() {
  const { watchId } = Route.useParams();
  return (
    <Guard scope="watches:read">
      <WatchDetail id={watchId} />
    </Guard>
  );
}
