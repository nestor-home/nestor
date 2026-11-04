import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { type FormEvent, type ReactElement, useState } from "react";
import { ApiError, api, keys, messageOf, type Secret, secretsQuery } from "@/api";
import { ConfirmFrame } from "@/components/confirm";
import { Field } from "@/components/field";
import { FormActions } from "@/components/form-actions";
import { useNotify } from "@/components/notices";
import { FormDialog } from "@/components/overlay-form";
import { Section } from "@/components/page";
import { Empty, Failure, FormError, Loading, Notice } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useT } from "@/i18n";

/** The vault: secrets the file refers to as `${secret:name}`, never shown, only replaced. */
export function SecretsPage() {
  const t = useT();
  const secrets = useQuery(secretsQuery);
  return (
    <>
      <h2 className="mb-2 font-serif text-[1.6rem] leading-tight text-ink">{t("cfg-secrets")}</h2>
      <p className="mb-8 max-w-2xl text-sm text-pretty text-ink-muted">{t("cfg-secrets-intro")}</p>
      <Section
        title={t("cfg-secrets-list")}
        count={secrets.data?.length}
        aside={
          <SecretForm
            trigger={
              <Button variant="outline" size="sm">
                <Plus /> {t("cfg-secret-new")}
              </Button>
            }
          />
        }
      >
        {secrets.isPending ? (
          <Loading lines={3} />
        ) : secrets.isError ? (
          <Failure error={secrets.error} retry={() => void secrets.refetch()} />
        ) : secrets.data.length ? (
          <ul className="divide-y divide-rule border-y border-rule">
            {secrets.data.map((s) => (
              <SecretRow key={s.name} secret={s} />
            ))}
          </ul>
        ) : (
          <Empty hint={t("cfg-secrets-empty-hint")}>{t("cfg-secrets-empty")}</Empty>
        )}
      </Section>
    </>
  );
}

function SecretRow({ secret: s }: { secret: Secret }) {
  const t = useT();
  return (
    <li className="flex flex-wrap items-start gap-x-4 gap-y-2 py-3.5">
      <KeyRound className="mt-1 size-4 text-ink-faint" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[0.85rem] [overflow-wrap:anywhere] text-ink">{s.name}</p>
        <p className="mt-0.5 text-[0.85rem] text-ink-muted">
          {s.set ? (
            t("cfg-secret-set", { preview: s.preview ?? "•••" })
          ) : (
            <span className="text-brick">{t("cfg-secret-unset")}</span>
          )}
        </p>
        <p className="mt-1 text-xs text-ink-muted">
          {s.used_by.length ? (
            <>
              {t("cfg-secret-used-by")}{" "}
              {s.used_by.map((path, i) => (
                <span key={path}>
                  {i > 0 ? ", " : null}
                  <code className="text-[0.85rem] text-ink">{path}</code>
                </span>
              ))}
            </>
          ) : (
            t("cfg-secret-unused")
          )}
        </p>
      </div>
      <div className="flex items-center gap-1">
        <SecretForm
          name={s.name}
          trigger={
            <Button variant="outline" size="sm">
              {s.set ? t("cfg-secret-replace") : t("cfg-secret-define")}
            </Button>
          }
        />
        {s.set ? <DeleteSecret secret={s} /> : null}
      </div>
    </li>
  );
}

/** Setting a secret: a name (new ones only) and a value typed once, never shown again. */
function SecretForm({ name, trigger }: { name?: string; trigger: ReactElement }) {
  const t = useT();
  return (
    <FormDialog
      trigger={trigger}
      title={name ? t("cfg-secret-replace-title", { name }) : t("cfg-secret-new")}
      description={t("cfg-secret-form-text")}
    >
      {(close) => <SecretFields name={name} close={close} />}
    </FormDialog>
  );
}

function SecretFields({ name: fixed, close }: { name?: string; close: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const [name, setName] = useState(fixed ?? "");
  const [value, setValue] = useState("");
  const write = useMutation({
    mutationFn: () => api.setSecret(name.trim(), value),
    onSuccess: (s) => {
      void queryClient.invalidateQueries({ queryKey: keys.secrets });
      notify(t("cfg-secret-saved", { name: s.name }));
      close();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim() && value) write.mutate();
  };
  return (
    <form onSubmit={submit} className="grid gap-4">
      {fixed ? null : (
        <Field label={t("cfg-secret-name")} htmlFor="secret-name" hint={t("cfg-secret-name-hint")}>
          <Input
            id="secret-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="font-mono"
            spellCheck={false}
            autoComplete="off"
            required
          />
        </Field>
      )}
      <Field label={t("cfg-secret-value")} htmlFor="secret-value">
        <Input
          id="secret-value"
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoComplete="new-password"
          className="font-mono"
          required
        />
      </Field>
      <FormError error={write.error} />
      <FormActions>
        <Button type="button" variant="ghost" onClick={close}>
          {t("action-cancel")}
        </Button>
        <Button type="submit" variant="accent" disabled={write.isPending || !name.trim() || !value}>
          {write.isPending ? "…" : t("cfg-secret-save")}
        </Button>
      </FormActions>
    </form>
  );
}

/**
 * Deleting a secret: refused while the file refers to it (409 `secret_in_use`), which is said with
 * the places; deleting anyway leaves those references broken until the file changes.
 */
function DeleteSecret({ secret: s }: { secret: Secret }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const [open, setOpen] = useState(false);
  const [refused, setRefused] = useState<ApiError | null>(null);
  const remove = useMutation({
    mutationFn: (force: boolean) => api.deleteSecret(s.name, force),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.secrets });
      notify(t("cfg-secret-deleted", { name: s.name }));
      setOpen(false);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) setRefused(error);
    },
  });
  return (
    <ConfirmFrame
      open={open}
      onOpenChange={(next) => {
        if (remove.isPending) return;
        setOpen(next);
        if (!next) {
          setRefused(null);
          remove.reset();
        }
      }}
      trigger={
        <Button variant="ghost" size="icon-sm" aria-label={t("cfg-secret-delete-label", { name: s.name })}>
          <Trash2 />
        </Button>
      }
      title={t("cfg-secret-delete-title", { name: s.name })}
      description={refused ? t("cfg-secret-in-use-text") : t("cfg-secret-delete-text")}
      details={refused ? <Notice>{messageOf(refused)}</Notice> : <FormError error={remove.error} />}
      busy={remove.isPending}
      action={
        <Button variant="destructive" onClick={() => remove.mutate(Boolean(refused))} disabled={remove.isPending}>
          {remove.isPending ? "…" : refused ? t("cfg-secret-delete-anyway") : t("cfg-secret-delete")}
        </Button>
      }
    />
  );
}
