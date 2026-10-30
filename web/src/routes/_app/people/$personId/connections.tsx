import { createFileRoute } from "@tanstack/react-router";
import { PersonConnections, usePerson } from "@/features/people/people";

export const Route = createFileRoute("/_app/people/$personId/connections")({ component: Page });

function Page() {
  const { personId } = Route.useParams();
  const { person } = usePerson(personId);
  return person ? <PersonConnections person={person} /> : null;
}
