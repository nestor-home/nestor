import { ChevronRight } from "lucide-react";
import { type FormEvent, useState } from "react";
import type { Connection, Connector } from "@/api";
import { ApiError } from "@/api/client";
import { CopyField } from "@/components/copy-field";
import { Field } from "@/components/field";
import { PersonPicker } from "@/components/person-picker";
import { FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { useConnect } from "./connect-flow";

const BUTTON = {
  idle: "conn-connect",
  pending: "conn-connecting",
  redirecting: "conn-redirecting",
  connected: "conn-connected",
  failed: "conn-connect",
} as const;

type FieldSpec = Connector["fields"][number];

export function ConnectForm({
  connector,
  replaces,
  onConnected,
}: {
  connector: Connector;
  replaces: string | null;
  onConnected: (connection: Connection) => void;
}) {
  const t = useT();
  const oauth = connector.auth === "oauth2";
  const discovered = connector.auth === "discovered";
  const [person, setPerson] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const { phase, connect, error } = useConnect(connector.kind, connector.auth, onConnected);
  const blocked = oauth && !connector.oauth?.registered;
  const busy = phase === "pending" || phase === "redirecting";
  const clientRequired = error instanceof ApiError && error.code === "client_required";
  // a server found by its address: what it may ask besides the address waits behind a disclosure
  const [main, extra] = discovered
    ? [connector.fields.filter((f) => f.default === null), connector.fields.filter((f) => f.default !== null)]
    : [connector.fields, []];

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v.trim()]));
    connect({ person: person || null, replaces, values: oauth ? {} : trimmed });
  }

  // credentials go with the server they were typed for: another server starts without them
  const elsewhere = (v: Record<string, string>) =>
    Object.fromEntries(Object.entries(v).filter(([name]) => !extra.some((f) => f.name === name)));
  const set = (name: string, value: string) =>
    setValues((v) => ({ ...(main.some((f) => f.name === name) ? elsewhere(v) : v), [name]: value }));
  const input = (f: FieldSpec) => (
    <FieldInput
      key={f.name}
      field={f}
      kept={Boolean(replaces) && discovered}
      value={values[f.name] ?? ""}
      onChange={(value) => set(f.name, value)}
    />
  );

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
        {connector.presets.length ? (
          <Presets
            connector={connector}
            values={values}
            onPick={(picked) => setValues((v) => ({ ...elsewhere(v), ...picked }))}
          />
        ) : null}
        {oauth ? null : main.map(input)}
        {extra.length ? (
          <Collapsible key={clientRequired ? "asked" : "closed"} defaultOpen={clientRequired}>
            <CollapsibleTrigger className="group/auth inline-flex items-center gap-1.5 rounded-sm font-mono text-[0.72rem] tracking-wide text-ink-muted uppercase hover:text-ink">
              <ChevronRight
                className="size-3.5 transition-transform group-data-panel-open/auth:rotate-90"
                aria-hidden="true"
              />
              {t("conn-credentials")}
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="mt-4 grid gap-4 border-t border-dashed border-rule pt-4">
                {extra.map(input)}
                {clientRequired && connector.oauth ? (
                  <div className="grid gap-1.5">
                    <p className="text-[0.8rem] font-medium">{t("conn-redirect-uri-service")}</p>
                    <CopyField value={connector.oauth.redirect_uri} label={t("conn-redirect-uri-label")} />
                  </div>
                ) : null}
              </div>
            </CollapsibleContent>
          </Collapsible>
        ) : null}
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

/** One field of the connector; `kept`: reconnecting, what is left empty is kept from the broken account. */
function FieldInput({
  field: f,
  kept,
  value,
  onChange,
}: {
  field: FieldSpec;
  kept: boolean;
  value: string;
  onChange: (v: string) => void;
}) {
  const t = useT();
  const required = f.default === null && !kept;
  return (
    <Field
      label={f.default !== null ? t("conn-field-optional", { label: f.label }) : f.label}
      htmlFor={`field-${f.name}`}
      hint={kept ? t("conn-field-kept") : undefined}
    >
      <Input
        id={`field-${f.name}`}
        name={f.name}
        type={f.secret ? "password" : "text"}
        autoComplete={f.secret ? "new-password" : "off"}
        spellCheck={false}
        required={required}
        placeholder={f.default ? `${f.default}…` : undefined}
        className={f.secret ? undefined : "font-mono"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}

/** Well-known services of the connector: picking one fills the fields with its values. */
function Presets({
  connector,
  values,
  onPick,
}: {
  connector: Connector;
  values: Record<string, string>;
  onPick: (values: Record<string, string>) => void;
}) {
  const t = useT();
  const picked = connector.presets.find((p) => Object.entries(p.values).every(([k, v]) => values[k] === v));
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-2 text-[0.8rem] font-medium text-ink">{t("conn-presets")}</legend>
      <ToggleGroup
        aria-label={t("conn-presets")}
        value={picked ? [picked.name] : []}
        onValueChange={(value: string[]) => {
          const next = connector.presets.find((p) => p.name === value.find((v) => v !== picked?.name));
          if (next) onPick(next.values);
        }}
        className="grid w-full grid-cols-2 gap-2 sm:grid-cols-3"
      >
        {connector.presets.map((p) => (
          <ToggleGroupItem
            key={p.name}
            value={p.name}
            className="h-auto w-full min-w-0 justify-start gap-2 rounded-md border border-rule bg-paper-raised px-2.5 py-2 text-left text-sm hover:border-rule-strong data-[pressed]:border-ember data-[pressed]:bg-ember-soft/40"
          >
            <KindMark kind={p.brand ?? connector.kind} label={false} className="size-4 shrink-0 text-ink" />
            <span className="truncate">{p.name}</span>
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </fieldset>
  );
}
