import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { connectorQuery } from "@/api";
import { FormSheet } from "@/components/overlay-form";
import { Failure, Loading } from "@/components/states";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { ConnectForm } from "./connect-form";
import { OAuthClientSection } from "./oauth-client";

/** Connecting a service, in a sheet over the catalogue: its guide, its OAuth client, the form. */
export function ConnectSheet({
  kind,
  replaces,
  onClose,
}: {
  kind: string | undefined;
  replaces: string | undefined;
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
          <div className="grid gap-8 pt-6">
            <p className="flex items-center gap-2 font-mono text-xs text-ink-muted">
              <KindMark kind={connector.data.brand ?? connector.data.kind} className="size-4 text-ink" />
              {connector.data.kind}
            </p>
            {connector.data.auth === "oauth2" ? <OAuthClientSection connector={connector.data} /> : null}
            <ConnectForm
              connector={connector.data}
              replaces={replaces ?? null}
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
