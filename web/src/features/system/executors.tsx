import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type ExecutorInfo, executorsQuery, type IssuedKey, keys } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { CopyButton, CopyField } from "@/components/copy-field";
import { FormDialog } from "@/components/overlay-form";
import { RowList, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { BrandMark, brandOf } from "@/lib/brands";
import { useCan } from "@/lib/session";

/**
 * The executors and their keys for Nestor's MCP server: what each reaches while it works, when its key was made and
 * last used; making, renewing and revoking a key for who manages the configuration. A key is shown once, in the dialog
 * that follows its making, with what to paste in an executor's own configuration.
 */
export function ExecutorsSection() {
  const t = useT();
  const executors = useQuery(executorsQuery);
  const canManage = useCan("config:manage");
  if (!executors.data?.executors.length) return null;
  const { url } = executors.data;
  return (
    <Section title={t("sys-executors")} count={executors.data.executors.length}>
      <p className="mb-3 max-w-prose text-[0.85rem] text-ink-muted">
        {url ? t("sys-executors-intro", { url }) : t("sys-executors-off")}
      </p>
      <RowList>
        {executors.data.executors.map((executor) => (
          <ExecutorRow key={executor.name} executor={executor} manage={canManage && url !== null} />
        ))}
      </RowList>
    </Section>
  );
}

/** Making a first key, or renewing it: the same action, said otherwise. */
const MAKE = { label: "sys-executor-key-make", title: "sys-executor-make-title", body: "sys-executor-make-body" };
const RENEW = { label: "sys-executor-key-renew", title: "sys-executor-renew-title", body: "sys-executor-renew-body" };

function ExecutorRow({ executor, manage }: { executor: ExecutorInfo; manage: boolean }) {
  const t = useT();
  const queryClient = useQueryClient();
  const [issued, setIssued] = useState<IssuedKey | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.executors });
  const issue = useMutation({
    mutationFn: () => api.issueExecutorKey(executor.name),
    onSuccess: (key) => {
      setIssued(key);
      void refresh();
    },
  });
  const revoke = useMutation({ mutationFn: () => api.revokeExecutorKey(executor.name), onSuccess: refresh });
  const brand = brandOf(executor.name);
  const { key } = executor;
  const making = key ? RENEW : MAKE;
  return (
    <li className="grid grid-cols-[1.5rem_minmax(0,1fr)] items-start gap-x-4 gap-y-2 px-5 py-3 sm:grid-cols-[1.5rem_minmax(0,1fr)_auto]">
      {brand ? <BrandMark brand={brand} className="mt-0.5 size-4.5 text-ink" /> : <span />}
      <div className="min-w-0">
        <p className="text-ink">{executor.name}</p>
        <p className="text-[0.85rem] text-ink-muted">{t("sys-executor-tools", { tools: executor.nestor_tools })}</p>
        <p className="mt-0.5 text-xs text-ink-faint">
          {key ? (
            <>
              {t("sys-executor-key-made")} <Ago iso={key.issued_at} />
              {" · "}
              {key.last_used_at ? (
                <>
                  {t("sys-executor-key-used")} <Ago iso={key.last_used_at} />
                </>
              ) : (
                t("sys-executor-key-unused")
              )}
            </>
          ) : (
            t("sys-executor-no-key")
          )}
        </p>
      </div>
      {manage ? (
        <div className="col-start-2 flex flex-wrap gap-2 sm:col-start-3 sm:justify-end">
          <Confirm
            trigger={
              <Button size="sm" variant={key ? "secondary" : "accent"}>
                {t(making.label)}
              </Button>
            }
            title={t(making.title, { name: executor.name })}
            confirm={t(making.label)}
            tone={key ? "destructive" : "accent"}
            onConfirm={() => issue.mutateAsync()}
          >
            {t(making.body, { name: executor.name, tools: executor.nestor_tools })}
          </Confirm>
          {key ? (
            <Confirm
              trigger={
                <Button size="sm" variant="destructive">
                  {t("sys-executor-key-revoke")}
                </Button>
              }
              title={t("sys-executor-revoke-title", { name: executor.name })}
              confirm={t("sys-executor-key-revoke")}
              onConfirm={() => revoke.mutateAsync()}
            >
              {t("sys-executor-revoke-body", { name: executor.name })}
            </Confirm>
          ) : null}
        </div>
      ) : null}
      <FormDialog
        open={issued !== null}
        onOpenChange={(open) => (open ? null : setIssued(null))}
        title={t("sys-executor-key-title", { name: executor.name })}
        description={t("sys-executor-key-once")}
        wide
      >
        {(close) => (issued ? <IssuedKeyView executor={executor} issued={issued} close={close} /> : null)}
      </FormDialog>
    </li>
  );
}

/** The key just made, once; for an executor configured by hand, what to add to its configuration. */
function IssuedKeyView({ executor, issued, close }: { executor: ExecutorInfo; issued: IssuedKey; close: () => void }) {
  const t = useT();
  return (
    <div className="grid gap-4">
      <CopyField value={issued.key} label={t("sys-executor-key-label")} />
      {issued.setup ? (
        <div className="grid gap-2">
          <p className="text-[0.85rem] text-ink-muted">{t("sys-executor-profile", { name: executor.name })}</p>
          <div className="relative">
            <pre className="overflow-x-auto rounded-md border border-rule-strong bg-paper-sunken px-3 py-2 pr-20 font-mono text-[0.75rem] text-ink">
              {issued.setup}
            </pre>
            <div className="absolute top-1.5 right-1.5">
              <CopyButton value={issued.setup} label={t("sys-executor-setup-label")} />
            </div>
          </div>
        </div>
      ) : (
        <p className="text-[0.85rem] text-ink-muted">{t("sys-executor-passed", { name: executor.name })}</p>
      )}
      <Button className="justify-self-end" onClick={close}>
        {t("action-close")}
      </Button>
    </div>
  );
}
