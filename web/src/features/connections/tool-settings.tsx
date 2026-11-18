import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, type ConnectionDetail, keys } from "@/api";
import { useNotify } from "@/components/notices";
import { RowList, Section } from "@/components/page";
import { RiskTag } from "@/components/risk-tag";
import { Empty, FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n";

/** Which tools the assistant gets from this account, each with its risk, and whether writing asks first. */
export function ToolSettings({ connection, editable }: { connection: ConnectionDetail; editable: boolean }) {
  const queryClient = useQueryClient();
  const notify = useNotify();
  const t = useT();
  const initial = () => new Set(connection.tools.filter((tool) => tool.enabled).map((tool) => tool.name));
  const [enabled, setEnabled] = useState(initial);
  const [confirmWrites, setConfirmWrites] = useState(connection.confirm_writes);
  const changed =
    confirmWrites !== connection.confirm_writes ||
    connection.tools.some((tool) => tool.enabled !== enabled.has(tool.name));

  const save = useMutation({
    mutationFn: () =>
      api.configureTools(connection.id, {
        disabled_tools: connection.tools.filter((tool) => !enabled.has(tool.name)).map((tool) => tool.name),
        confirm_writes: confirmWrites,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.connection(connection.id), updated);
      notify(t("conn-tools-saved"));
    },
  });

  function toggle(name: string, on: boolean) {
    setEnabled((current) => {
      const next = new Set(current);
      if (on) next.add(name);
      else next.delete(name);
      return next;
    });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  if (connection.tools.length === 0) {
    return (
      <div className="grid gap-10">
        <Section title={t("conn-tools")}>
          <Empty>{t("conn-no-tools")}</Empty>
        </Section>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="grid gap-10">
      <Section
        title={t("conn-tools")}
        count={enabled.size}
        aside={
          editable ? (
            <Button type="submit" size="sm" disabled={!changed || save.isPending}>
              {save.isPending ? t("action-saving") : t("action-save")}
            </Button>
          ) : (
            <span className="text-meta text-ink-muted">{t("conn-read-only")}</span>
          )
        }
      >
        {changed ? <p className="-mt-2 mb-3 text-body text-amber">{t("conn-unsaved")}</p> : null}
        <FormError error={save.error} />
        <label htmlFor="confirm-writes" className="surface mb-3 flex items-start gap-3 px-4 py-3.5">
          <Checkbox
            id="confirm-writes"
            checked={confirmWrites}
            onCheckedChange={(on) => setConfirmWrites(on)}
            disabled={!editable}
            className="mt-0.5"
          />
          <span className="text-body text-ink">
            {t("conn-confirm-writes")}
            <span className="block text-body text-ink-muted">{t("conn-confirm-writes-hint")}</span>
          </span>
        </label>
        <RowList>
          {connection.tools.map((tool) => {
            const id = `tool-${tool.name}`;
            return (
              <li key={tool.name} className="flex items-start gap-4 px-4 py-3.5">
                <div className="min-w-0 flex-1">
                  <label htmlFor={id} className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <code className="font-mono text-meta [overflow-wrap:anywhere] text-ink">{tool.name}</code>
                    <RiskTag risk={tool.risk} />
                  </label>
                  <p id={`${id}-description`} className="mt-0.5 text-body text-ink-muted">
                    {tool.description}
                  </p>
                </div>
                <Switch
                  id={id}
                  checked={enabled.has(tool.name)}
                  onCheckedChange={(on) => toggle(tool.name, on)}
                  disabled={!editable}
                  aria-describedby={`${id}-description`}
                  className="mt-0.5"
                />
              </li>
            );
          })}
        </RowList>
      </Section>
    </form>
  );
}
