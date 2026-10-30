import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { AccountsHeader, AccountsList } from "@/features/accounts/accounts";

export const Route = createFileRoute("/_app/accounts/")({ component: Page });

function Page() {
  return (
    <Guard scope="accounts:read">
      <AccountsHeader />
      <AccountsList />
    </Guard>
  );
}
