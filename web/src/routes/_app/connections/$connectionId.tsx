import { useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Outlet, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { connectionQuery, keys } from "@/api";
import { Guard } from "@/components/guard";
import { useNotify } from "@/components/notices";
import { ConnectionFrame } from "@/features/connections/connection-detail";
import { useT } from "@/i18n";

export const Route = createFileRoute("/_app/connections/$connectionId")({
  // the provider brings the browser back here with `connected=1` once the account is plugged in
  validateSearch: (search: Record<string, unknown>): { connected?: 1 } =>
    search.connected === 1 || search.connected === "1" ? { connected: 1 } : {},
  component: ConnectionLayout,
});

function ConnectionLayout() {
  const { connectionId } = Route.useParams();
  const { connected } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const queryClient = useQueryClient();
  const notify = useNotify();
  const t = useT();

  useEffect(() => {
    if (!connected) return;
    void queryClient.invalidateQueries({ queryKey: keys.connections });
    void queryClient.fetchQuery(connectionQuery(connectionId)).then(
      (c) => notify(t("conn-account-connected", { account: c.account })),
      () => undefined,
    );
    void navigate({ search: {}, replace: true });
  }, [connected, connectionId, navigate, notify, queryClient, t]);

  return (
    <Guard scope="connections:read">
      <ConnectionFrame id={connectionId}>
        <Outlet />
      </ConnectionFrame>
    </Guard>
  );
}
