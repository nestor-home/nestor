import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Guard } from "@/components/guard";
import { PageHeader } from "@/components/page";
import { ConnectSheet } from "@/features/connections/connect-sheet";
import { Catalogue } from "@/features/connections/connections-overview";
import { ConnectionsTabs } from "@/features/connections/tabs";
import { useT } from "@/i18n";

interface Search {
  connect?: string; // the connector whose sheet is open
  replaces?: string; // the broken connection being reconnected
}

export const Route = createFileRoute("/_app/connections/catalogue")({
  validateSearch: (search: Record<string, unknown>): Search => ({
    ...(typeof search.connect === "string" && search.connect ? { connect: search.connect } : {}),
    ...(typeof search.replaces === "string" && search.replaces ? { replaces: search.replaces } : {}),
  }),
  component: CataloguePage,
});

function CataloguePage() {
  const { connect, replaces } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const t = useT();
  return (
    <Guard scope="connections:read">
      <PageHeader title={t("conn-title")} />
      <ConnectionsTabs />
      <Catalogue onConnect={(kind) => void navigate({ search: { connect: kind } })} />
      <ConnectSheet kind={connect} replaces={replaces} onClose={() => void navigate({ search: {} })} />
    </Guard>
  );
}
