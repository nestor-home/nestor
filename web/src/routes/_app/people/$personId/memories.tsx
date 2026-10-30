import { createFileRoute } from "@tanstack/react-router";
import { PersonMemories, usePerson } from "@/features/people/people";

export const Route = createFileRoute("/_app/people/$personId/memories")({ component: Page });

function Page() {
  const { personId } = Route.useParams();
  const { person } = usePerson(personId);
  return person ? <PersonMemories person={person} /> : null;
}
