import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { HouseSpace } from "@/features/house/space";

export const Route = createFileRoute("/_app/house")({ component: Page });

function Page() {
  return (
    <Guard scope="people:read">
      <HouseSpace />
    </Guard>
  );
}
