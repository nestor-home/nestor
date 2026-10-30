import { createFileRoute } from "@tanstack/react-router";
import { PersonConversations, usePerson } from "@/features/people/people";

export const Route = createFileRoute("/_app/people/$personId/conversations")({ component: Page });

function Page() {
  const { personId } = Route.useParams();
  const { person } = usePerson(personId);
  return person ? <PersonConversations person={person} /> : null;
}
