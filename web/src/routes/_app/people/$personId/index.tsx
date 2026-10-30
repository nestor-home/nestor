import { createFileRoute } from "@tanstack/react-router";
import { PersonOverview, usePerson } from "@/features/people/people";

export const Route = createFileRoute("/_app/people/$personId/")({ component: Page });

function Page() {
  const { personId } = Route.useParams();
  const { person } = usePerson(personId);
  return person ? <PersonOverview person={person} /> : null;
}
