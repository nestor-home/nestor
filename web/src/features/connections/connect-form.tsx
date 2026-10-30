import { type FormEvent, useState } from "react";
import type { Connection, Connector } from "@/api";
import { Field } from "@/components/field";
import { PersonPicker } from "@/components/person-picker";
import { FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n";
import { useConnect } from "./connect-flow";

const BUTTON = {
  idle: "conn-connect",
  pending: "conn-connecting",
  redirecting: "conn-redirecting",
  connected: "conn-connected",
  failed: "conn-connect",
} as const;

export function ConnectForm({
  connector,
  replaces,
  onConnected,
  leave,
}: {
  connector: Connector;
  replaces: string | null;
  onConnected: (connection: Connection) => void;
  leave?: (url: string) => void;
}) {
  const t = useT();
  const oauth = connector.auth === "oauth2";
  const [person, setPerson] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const { phase, connect, error } = useConnect(connector.kind, connector.auth, {
    onConnected,
    ...(leave ? { leave } : {}),
  });
  const blocked = oauth && !connector.client;
  const busy = phase === "pending" || phase === "redirecting";

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim()]));
    connect({ person: person || null, replaces, values: oauth ? {} : trimmed });
  }

  return (
    <section aria-labelledby="connect-account" className="grid gap-4">
      <h3 id="connect-account" className="border-b border-rule pb-2 font-serif text-lg font-normal">
        {t("conn-connect-account")}
      </h3>
      {oauth ? (
        <p className="text-sm text-ink-muted">{t("conn-oauth-consent")}</p>
      ) : connector.setup ? (
        <p className="text-sm whitespace-pre-line text-ink-muted">{connector.setup}</p>
      ) : null}
      <form onSubmit={submit} className="grid gap-4">
        <Field label={t("conn-account-of")} htmlFor="person" hint={t("conn-account-of-hint")}>
          <PersonPicker id="person" value={person} onChange={setPerson} />
        </Field>
        {oauth
          ? null
          : connector.fields.map((f) => (
              <Field
                key={f.name}
                label={f.optional ? t("conn-field-optional", { label: f.label }) : f.label}
                htmlFor={`field-${f.name}`}
              >
                <Input
                  id={`field-${f.name}`}
                  name={f.name}
                  type={f.secret ? "password" : "text"}
                  autoComplete={f.secret ? "new-password" : "off"}
                  spellCheck={false}
                  required={!f.optional}
                  placeholder={f.placeholder ? `${f.placeholder}…` : undefined}
                  className={f.secret ? undefined : "font-mono"}
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                />
              </Field>
            ))}
        {blocked ? <p className="text-sm text-amber">{t("conn-client-first")}</p> : null}
        <FormError error={error} />
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={blocked || busy}>
            {t(BUTTON[phase])}
          </Button>
          {busy ? (
            <span role="status" className="font-mono text-xs text-ink-muted">
              {phase === "redirecting" ? t("conn-status-redirecting") : t("conn-status-pending")}
            </span>
          ) : null}
        </div>
      </form>
    </section>
  );
}
