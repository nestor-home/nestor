import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { AccountsHeader, InvitationsList } from "@/features/accounts/accounts";

export const Route = createFileRoute("/_app/accounts/invitations")({ component: Page });

function Page() {
  return (
    <Guard scope="accounts:write">
      <AccountsHeader />
      <InvitationsList />
    </Guard>
  );
}
