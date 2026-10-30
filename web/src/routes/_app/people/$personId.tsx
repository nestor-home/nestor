import { createFileRoute, Outlet } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PersonFrame } from "@/features/people/people";

export const Route = createFileRoute("/_app/people/$personId")({ component: Layout });

function Layout() {
  const { personId } = Route.useParams();
  return (
    <Guard scope="people:read">
      <PersonFrame id={personId}>
        <Outlet />
      </PersonFrame>
    </Guard>
  );
}
