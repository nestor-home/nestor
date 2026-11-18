import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { connectorQuery } from "@/api";
import { ServiceTile } from "@/components/marks";
import { FormSheet } from "@/components/overlay-form";
import { Failure, Loading } from "@/components/states";
import { useT } from "@/i18n";
import { authLabel } from "@/lib/labels";
import { ConnectForm } from "./connect-form";
import { OAuthClientSection } from "./oauth-client";

/** Connecting a service, in a sheet over the catalogue: its logo, its OAuth client, the form. */
export function ConnectSheet({
  kind,
  replaces,
  preset,
  onClose,
}: {
  kind: string | undefined;
  replaces: string | undefined;
  preset: string | undefined; // the known server to start from
  onClose: () => void;
}) {
  const connector = useQuery({ ...connectorQuery(kind ?? ""), enabled: Boolean(kind) });
  const navigate = useNavigate();
  const t = useT();
  return (
    <FormSheet
      open={Boolean(kind)}
      onOpenChange={(open) => !open && onClose()}
      title={connector.data?.title ?? t("conn-connect")}
      description={replaces ? t("conn-reconnect-note") : connector.data?.description}
    >
      {() =>
        connector.isPending ? (
          <Loading lines={3} />
        ) : connector.isError ? (
          <Failure error={connector.error} retry={() => void connector.refetch()} />
        ) : (
          <div className="grid gap-7 pt-6">
            <p className="flex items-center gap-3 text-[0.9rem] text-ink-muted">
              <ServiceTile kind={connector.data.brand ?? connector.data.kind} />
              <span>
                {authLabel(connector.data.auth)}
                {connector.data.inbound.length ? ` · ${t("conn-feeds-watches")}` : ""}
              </span>
            </p>
            {connector.data.auth === "oauth2" ? <OAuthClientSection connector={connector.data} /> : null}
            <ConnectForm
              connector={connector.data}
              replaces={replaces ?? null}
              preset={preset}
              onConnected={(c) =>
                void navigate({
                  to: "/connections/$connectionId",
                  params: { connectionId: c.id },
                  search: { connected: 1 },
                })
              }
            />
          </div>
        )
      }
    </FormSheet>
  );
}
