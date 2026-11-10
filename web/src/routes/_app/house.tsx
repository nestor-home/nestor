import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { HouseView } from "@/features/house/house-view";

export const Route = createFileRoute("/_app/house")({ component: Page });

function Page() {
  return (
    <Guard scope="home:read">
      <HouseView />
    </Guard>
  );
}
