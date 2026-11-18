import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { AccountsView } from "@/features/accounts/accounts";

export const Route = createFileRoute("/_app/accounts/")({ component: Page });

function Page() {
  return (
    <Guard scope="accounts:read">
      <AccountsView />
    </Guard>
  );
}
