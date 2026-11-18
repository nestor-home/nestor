import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, RotateCcw } from "lucide-react";
import { useState } from "react";
import { ApiError, api, configHistoryQuery, configVersionQuery, type HistoryEntry, keys } from "@/api";
import { Ago } from "@/components/ago";
import { CardHead, OpenArrow } from "@/components/card";
import { Confirm } from "@/components/confirm";
import { IconTile } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { SheetPanel, SideSheet } from "@/components/overlay-form";
import { Section } from "@/components/page";
import { Empty, Failure, Loading, Notice } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { clock, dayLabel } from "@/lib/dates";
import { Changes } from "./changes";
import { ConfigFrame } from "./config-layout";
import { changeCount, useConfigEditor } from "./editor";
import { Problems } from "./fields";

/** Earlier files, newest first: one opens beside the list with what restoring it would change. */
export function HistoryPage() {
  const t = useT();
  const history = useQuery(configHistoryQuery);
  const [opened, setOpened] = useState<HistoryEntry | null>(null);
  return (
    <ConfigFrame title={t("cfg-history")} about={t("cfg-history-intro")}>
      <Section title={t("cfg-history-versions")} count={history.data?.length}>
        {history.isPending ? (
          <Loading lines={3} />
        ) : history.isError ? (
          <Failure error={history.error} retry={() => void history.refetch()} />
        ) : history.data.length ? (
          <ol className="grid gap-3">
            {history.data.map((entry) => (
              <li key={entry.id}>
                <button type="button" onClick={() => setOpened(entry)} className="group surface w-full p-4 text-left">
                  <CardHead
                    mark={<IconTile icon={History} />}
                    title={
                      <span className="first-letter:uppercase">
                        {dayLabel(entry.at)} · {clock(entry.at)}
                      </span>
                    }
                    line={
                      <>
                        <Ago iso={entry.at} /> · {t("cfg-history-size", { size: entry.size })}
                      </>
                    }
                    aside={<OpenArrow />}
                  />
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <Empty hint={t("cfg-history-empty-hint")}>{t("cfg-history-empty")}</Empty>
        )}
      </Section>
      <SideSheet open={Boolean(opened)} onOpenChange={(open) => !open && setOpened(null)}>
        {opened ? <Version entry={opened} onRestored={() => setOpened(null)} /> : null}
      </SideSheet>
    </ConfigFrame>
  );
}

/** An earlier file, opened: what restoring it would change, checked like any edit, then the restore itself. */
function Version({ entry, onRestored }: { entry: HistoryEntry; onRestored: () => void }) {
  const t = useT();
  const editor = useConfigEditor();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const version = useQuery(configVersionQuery(entry.id));
  // what restoring would do, checked like any edit (against the file as it is now)
  const preview = useQuery({
    queryKey: [...keys.configVersion(entry.id), "preview", JSON.stringify(editor.base)] as const,
    queryFn: ({ signal }) => api.previewConfig(version.data?.document ?? {}, signal),
    enabled: Boolean(version.data),
    retry: false,
  });
  const restore = useMutation({
    mutationFn: () => api.restoreConfig(entry.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.config });
      void queryClient.invalidateQueries({ queryKey: keys.me });
      void queryClient.invalidateQueries({ queryKey: keys.system });
      notify(t("cfg-restored"));
      onRestored();
    },
  });
  const refused = restore.error instanceof ApiError ? restore.error.problems : [];
  const problems = refused.length ? refused : (preview.data?.problems ?? []);
  const count = changeCount(preview.data?.diff ?? null);
  return (
    <SheetPanel
      icon={History}
      kind={t("cfg-history-kind")}
      title={`${dayLabel(entry.at)} · ${clock(entry.at)}`}
      description={preview.data ? (count ? t("cfg-history-would", { count }) : t("cfg-history-same")) : undefined}
      actions={
        <>
          <Confirm
            trigger={
              <Button variant="accent" disabled={!count || problems.length > 0 || editor.dirty}>
                <RotateCcw /> {t("cfg-restore")}
              </Button>
            }
            title={t("cfg-restore-title")}
            confirm={t("cfg-restore")}
            tone="accent"
            onConfirm={() => restore.mutateAsync()}
          >
            {t("cfg-restore-text")}
          </Confirm>
          {editor.dirty ? <p className="self-center text-meta text-ink-muted">{t("cfg-restore-dirty")}</p> : null}
        </>
      }
    >
      {version.isError ? (
        <Failure error={version.error} />
      ) : preview.isError ? (
        <Failure error={preview.error} />
      ) : preview.data ? (
        <>
          {problems.length ? (
            <Notice>
              <p className="mb-1.5">{t("cfg-history-invalid")}</p>
              <Problems problems={problems} />
            </Notice>
          ) : null}
          <Changes diff={preview.data.diff} />
        </>
      ) : (
        <Loading lines={3} />
      )}
    </SheetPanel>
  );
}
