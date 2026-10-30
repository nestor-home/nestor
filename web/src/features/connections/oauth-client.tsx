import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, type Connector, keys } from "@/api";
import { CopyField } from "@/components/copy-field";
import { Field } from "@/components/field";
import { useNotify } from "@/components/notices";
import { FormDialog } from "@/components/overlay-form";
import { FormError } from "@/components/states";
import { Status } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n";

/** The household's own OAuth client at the provider (Home Assistant's "application credentials"). */
export function OAuthClientSection({ connector }: { connector: Connector }) {
  const registered = connector.client;
  const t = useT();
  return (
    <section aria-labelledby="oauth-client" className="grid gap-4">
      <div className="flex items-center justify-between gap-3 border-b border-rule pb-2">
        <h3 id="oauth-client" className="font-serif text-lg font-normal">
          {t("conn-client-title")}
        </h3>
        {registered ? (
          <Status tone="ok">{t("conn-client-registered")}</Status>
        ) : (
          <Status tone="attention">{t("conn-client-missing")}</Status>
        )}
      </div>
      {registered ? (
        <p className="text-sm text-ink-muted">
          {t("conn-client-id")} <code className="text-ink">{registered.client_id}</code>
        </p>
      ) : (
        <>
          <p className="text-sm text-ink-muted">{t("conn-client-why")}</p>
          {connector.setup ? (
            <ol className="grid gap-1.5 text-sm text-ink">
              {connector.setup
                .split("\n")
                .filter(Boolean)
                .map((step) => (
                  <li key={step} className="flex gap-2">
                    <span aria-hidden="true" className="font-mono text-xs text-ink-faint">
                      {step.match(/^\d+/)?.[0] ?? "·"}
                    </span>
                    <span>{step.replace(/^\d+\.\s*/, "")}</span>
                  </li>
                ))}
            </ol>
          ) : null}
        </>
      )}
      {connector.redirect_uri ? (
        <div className="grid gap-1.5">
          <p className="text-[0.8rem] font-medium">{t("conn-redirect-uri")}</p>
          <CopyField value={connector.redirect_uri} label={t("conn-redirect-uri-label")} />
          {connector.relayed ? <p className="text-xs text-ink-muted">{t("conn-relayed")}</p> : null}
        </div>
      ) : null}
      <FormDialog
        trigger={
          <Button variant={registered ? "ghost" : "default"} size="sm" className="justify-self-start">
            {registered ? t("conn-client-replace-ellipsis") : t("conn-client-register-ellipsis")}
          </Button>
        }
        title={registered ? t("conn-client-replace-title") : t("conn-client-register-title")}
        description={registered ? t("conn-client-replace-note") : undefined}
      >
        {(close) => <ClientForm connector={connector} onDone={close} />}
      </FormDialog>
    </section>
  );
}

function ClientForm({ connector, onDone }: { connector: Connector; onDone: () => void }) {
  const queryClient = useQueryClient();
  const notify = useNotify();
  const t = useT();
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const save = useMutation({
    mutationFn: () => api.setClient(connector.kind, { client_id: clientId.trim(), client_secret: secret.trim() }),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.connector(connector.kind), updated);
      void queryClient.invalidateQueries({ queryKey: keys.connectors });
      notify(t("conn-client-saved"));
      onDone();
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }
  return (
    <form onSubmit={submit} className="grid gap-4">
      <Field label={t("conn-client-id-field")} htmlFor="client_id">
        <Input
          id="client_id"
          autoComplete="off"
          spellCheck={false}
          required
          className="font-mono"
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
        />
      </Field>
      <Field label={t("conn-client-secret-field")} htmlFor="client_secret">
        <Input
          id="client_secret"
          type="password"
          autoComplete="new-password"
          required
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
        />
      </Field>
      <FormError error={save.error} />
      <Button type="submit" disabled={save.isPending} className="justify-self-end">
        {save.isPending ? t("action-saving") : t("conn-client-register")}
      </Button>
    </form>
  );
}
