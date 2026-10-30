import { createFileRoute } from "@tanstack/react-router";
import { PersonPresence, usePerson } from "@/features/people/people";

export const Route = createFileRoute("/_app/people/$personId/presence")({ component: Page });

function Page() {
  const { personId } = Route.useParams();
  const { person } = usePerson(personId);
  return person ? <PersonPresence person={person} /> : null;
}
