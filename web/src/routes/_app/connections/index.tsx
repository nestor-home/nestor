import { createFileRoute, Link } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { buttonVariants } from "@/components/ui/button";
import { ConnectedAccounts } from "@/features/connections/connections-overview";
import { ConnectionsTabs } from "@/features/connections/tabs";
import { useT } from "@/i18n";
import { useCan, useMe } from "@/lib/session";

export const Route = createFileRoute("/_app/connections/")({ component: Connections });

function Connections() {
  const me = useMe();
  const canConnect = useCan("connections:write");
  const t = useT();
  return (
    <Guard scope="connections:read">
      <PageHeader
        title={t("conn-title")}
        actions={
          canConnect ? (
            <Link to="/connections/catalogue" className={buttonVariants()}>
              <Plus aria-hidden="true" /> {t("conn-connect-service")}
            </Link>
          ) : null
        }
      >
        {t("conn-intro", { assistant: me.assistant })}
      </PageHeader>
      <ConnectionsTabs />
      <ConnectedAccounts />
    </Guard>
  );
}
