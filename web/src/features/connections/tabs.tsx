import { useQuery } from "@tanstack/react-query";
import { connectionsQuery, connectorsQuery } from "@/api";
import { TabNav } from "@/components/tab-nav";
import { useT } from "@/i18n";

export function ConnectionsTabs() {
  const connections = useQuery(connectionsQuery);
  const connectors = useQuery(connectorsQuery);
  const t = useT();
  return (
    <TabNav
      label={t("conn-title")}
      tabs={[
        { to: "/connections", label: t("conn-tab-accounts"), count: connections.data?.length },
        { to: "/connections/catalogue", label: t("conn-tab-catalogue"), count: connectors.data?.length },
      ]}
    />
  );
}
