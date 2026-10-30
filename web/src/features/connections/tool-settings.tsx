import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, type ConnectionDetail, keys, type Risk } from "@/api";
import { useNotify } from "@/components/notices";
import { Panel } from "@/components/page";
import { Empty, FormError } from "@/components/states";
import { Tag } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n";
import { riskLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

const RISK_TONE: Record<Risk, string> = {
  read: "",
  write: "border-amber/50 text-amber",
  sensitive: "border-brick/50 text-brick",
};

/** Which tools the assistant gets from this account, and whether writing asks first. */
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

  return (
    <Panel as="section">
      <h2 className="text-xl font-normal">{t("conn-tools")}</h2>
      {connection.tools.length === 0 ? (
        <Empty className="mt-4">{t("conn-no-tools")}</Empty>
      ) : (
        <form onSubmit={submit} className="mt-4">
          <ul className="divide-y divide-rule border-y border-rule">
            {connection.tools.map((tool) => {
              const id = `tool-${tool.name}`;
              return (
                <li key={tool.name} className="flex items-start gap-4 py-3">
                  <Switch
                    id={id}
                    checked={enabled.has(tool.name)}
                    onCheckedChange={(on) => toggle(tool.name, on)}
                    disabled={!editable}
                    aria-describedby={`${id}-description`}
                    className="mt-0.5"
                  />
                  <div className="min-w-0 flex-1">
                    <label htmlFor={id} className="flex flex-wrap items-center gap-2">
                      <code className="text-[0.82rem] text-ink">{tool.name}</code>
                      <Tag className={cn(RISK_TONE[tool.risk])}>{riskLabel(tool.risk)}</Tag>
                    </label>
                    <p id={`${id}-description`} className="mt-0.5 text-sm text-ink-muted">
                      {tool.description}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
          <label htmlFor="confirm-writes" className="mt-5 flex items-start gap-3">
            <Checkbox
              id="confirm-writes"
              checked={confirmWrites}
              onCheckedChange={(on) => setConfirmWrites(on)}
              disabled={!editable}
              className="mt-0.5"
            />
            <span className="text-sm">
              {t("conn-confirm-writes")}
              <span className="block text-ink-muted">{t("conn-confirm-writes-hint")}</span>
            </span>
          </label>
          <FormError error={save.error} />
          {editable ? (
            <div className="mt-5 flex items-center gap-3">
              <Button type="submit" disabled={!changed || save.isPending}>
                {save.isPending ? t("action-saving") : t("action-save")}
              </Button>
              {changed ? <span className="font-mono text-xs text-amber">{t("conn-unsaved")}</span> : null}
            </div>
          ) : null}
        </form>
      )}
    </Panel>
  );
}
