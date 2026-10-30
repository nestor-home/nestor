import { createFileRoute } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { AccountDetail } from "@/features/accounts/accounts";

export const Route = createFileRoute("/_app/accounts/$accountId")({ component: Page });

function Page() {
  const { accountId } = Route.useParams();
  return (
    <Guard scope="accounts:read">
      <AccountDetail id={accountId} />
    </Guard>
  );
}
