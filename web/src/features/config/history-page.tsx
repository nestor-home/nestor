import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, RotateCcw } from "lucide-react";
import { useState } from "react";
import { ApiError, api, configHistoryQuery, configVersionQuery, type HistoryEntry, keys } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { useNotify } from "@/components/notices";
import { Panel } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { clock, dayLabel } from "@/lib/dates";
import { cn } from "@/lib/utils";
import { Changes } from "./changes";
import { useConfigEditor } from "./editor";
import { Problems } from "./fields";

/** Earlier files, newest first: what restoring one would change, then the restore itself. */
export function HistoryPage() {
  const t = useT();
  const history = useQuery(configHistoryQuery);
  const [chosen, setChosen] = useState<string | null>(null);
  const selected = chosen ?? history.data?.[0]?.id ?? null;
  return (
    <>
      <h2 className="mb-2 font-serif text-[1.6rem] leading-tight text-ink">{t("cfg-history")}</h2>
      <p className="mb-8 max-w-2xl text-sm text-pretty text-ink-muted">{t("cfg-history-intro")}</p>
      {history.isPending ? (
        <Loading lines={3} />
      ) : history.isError ? (
        <Failure error={history.error} retry={() => void history.refetch()} />
      ) : history.data.length ? (
        <div className="grid gap-8 lg:grid-cols-[15rem_minmax(0,1fr)]">
          <ol aria-label={t("cfg-history-versions")} className="grid content-start gap-1">
            {history.data.map((entry) => (
              <li key={entry.id}>
                <Version entry={entry} current={entry.id === selected} onSelect={() => setChosen(entry.id)} />
              </li>
            ))}
          </ol>
          {selected ? <VersionDetail id={selected} /> : null}
        </div>
      ) : (
        <Empty hint={t("cfg-history-empty-hint")}>{t("cfg-history-empty")}</Empty>
      )}
    </>
  );
}

function Version({ entry, current, onSelect }: { entry: HistoryEntry; current: boolean; onSelect: () => void }) {
  const t = useT();
  return (
    <button
      type="button"
      aria-current={current ? "true" : undefined}
      onClick={onSelect}
      className={cn(
        "flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left hover:bg-paper-sunken focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ember",
        current && "bg-paper-sunken",
      )}
    >
      <History className={cn("mt-0.5 size-3.5", current ? "text-ember" : "text-ink-faint")} aria-hidden="true" />
      <span className="min-w-0">
        <span className="block text-sm text-ink">
          {dayLabel(entry.at)} · {clock(entry.at)}
        </span>
        <span className="block font-mono text-[0.7rem] text-ink-faint">
          <Ago iso={entry.at} /> · {t("cfg-history-size", { size: entry.size })}
        </span>
      </span>
    </button>
  );
}

function VersionDetail({ id }: { id: string }) {
  const t = useT();
  const editor = useConfigEditor();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const version = useQuery(configVersionQuery(id));
  // what restoring would do, checked like any edit (against the file as it is now)
  const preview = useQuery({
    queryKey: [...keys.configVersion(id), "preview", JSON.stringify(editor.base)] as const,
    queryFn: ({ signal }) => api.previewConfig(version.data?.document ?? {}, signal),
    enabled: Boolean(version.data),
    retry: false,
  });
  const restore = useMutation({
    mutationFn: () => api.restoreConfig(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.config });
      void queryClient.invalidateQueries({ queryKey: keys.me });
      void queryClient.invalidateQueries({ queryKey: keys.system });
      notify(t("cfg-restored"));
    },
  });
  if (version.isPending || preview.isPending) return <Loading lines={3} />;
  if (version.isError) return <Failure error={version.error} />;
  if (preview.isError) return <Failure error={preview.error} />;
  const refused = restore.error instanceof ApiError ? restore.error.problems : [];
  const problems = refused.length ? refused : preview.data.problems;
  const count = preview.data.diff.added.length + preview.data.diff.removed.length + preview.data.diff.changed.length;
  return (
    <Panel className="min-w-0">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-serif text-lg text-ink">
            {t("cfg-history-version", { day: dayLabel(version.data.at), time: clock(version.data.at) })}
          </p>
          <p className="mt-0.5 text-sm text-ink-muted">
            {count ? t("cfg-history-would", { count }) : t("cfg-history-same")}
          </p>
        </div>
        <Confirm
          trigger={
            <Button variant="outline" size="sm" disabled={!count || problems.length > 0 || editor.dirty}>
              <RotateCcw /> {t("cfg-restore")}
            </Button>
          }
          title={t("cfg-restore-title")}
          confirm={t("cfg-restore")}
          onConfirm={() => restore.mutateAsync()}
        >
          {t("cfg-restore-text")}
        </Confirm>
      </div>
      {editor.dirty ? <p className="mb-4 text-xs text-ink-muted">{t("cfg-restore-dirty")}</p> : null}
      {problems.length ? (
        <div className="mb-5 rounded-md border border-brick/40 bg-brick-soft/40 px-4 py-3">
          <p className="mb-1.5 text-sm text-ink">{t("cfg-history-invalid")}</p>
          <Problems problems={problems} />
        </div>
      ) : null}
      <Changes diff={preview.data.diff} />
    </Panel>
  );
}
