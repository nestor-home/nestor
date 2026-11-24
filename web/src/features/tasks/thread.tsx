/**
 * A task's thread, read like a conversation: each turn opens with the instruction someone gave (and the files sent
 * with it), then the executor's side: its steps while it works, then what it came back with (a report, a question, a
 * failure) and the files it handed back, and how that reached its person. Then the notes it kept for the task.
 */
import { CornerDownRight, NotebookPen, TriangleAlert } from "lucide-react";
import { type ReactNode, useEffect, useRef } from "react";
import type { TaskFile, TaskThread, TaskTurn } from "@/api";
import { API_BASE } from "@/api/client";
import { Ago } from "@/components/ago";
import { Avatar } from "@/components/marks";
import { Files } from "@/features/journal/attachments";
import { useT } from "@/i18n";
import { KindName, kindName } from "@/lib/brands";
import { hourMinute } from "@/lib/dates";
import { turnStatusLabel } from "@/lib/labels";
import { useMe } from "@/lib/session";
import { duration } from "@/lib/time";
import { cn } from "@/lib/utils";
import { Question, Steps } from "./parts";

/** Where the server serves a file of a turn. */
const fileUrl = (task: string, turn: string) => (index: number) =>
  `${API_BASE}/tasks/${task}/turns/${turn}/files/${index}`;

export function Thread({ task, follow = false }: { task: TaskThread; follow?: boolean }) {
  const t = useT();
  const end = useRef<HTMLLIElement>(null);
  const last = task.thread.at(-1)?.id;
  // in a sheet, the thread opens on its latest turn, as a conversation does
  useEffect(() => {
    if (follow && last) end.current?.scrollIntoView({ block: "end" });
  }, [follow, last]);
  return (
    <ol className="grid gap-8" aria-label={t("task-thread")}>
      {task.thread.map((turn, index) => (
        <li key={turn.id} ref={index === task.thread.length - 1 ? end : undefined} className="grid min-w-0 gap-4">
          <Said
            by={turn.by}
            at={turn.started_at}
            text={turn.instruction}
            files={
              <TurnFiles
                task={task}
                turn={turn}
                files={turn.files.filter((f) => f.given)}
                className="justify-items-end"
              />
            }
          />
          <Work task={task} turn={turn} />
          {turn.steered.map((steer) => (
            <Said key={steer.at} by={steer.by} at={steer.at} text={steer.instruction} steered />
          ))}
          <Outcome task={task} turn={turn} />
        </li>
      ))}
    </ol>
  );
}

/**
 * What someone said to the task, on the right as in a conversation: who and when, then the words. An instruction
 * that opened a turn carries its files; one given while the turn worked (`steered`) is marked as such.
 */
function Said({
  by,
  at,
  text,
  steered = false,
  files,
}: {
  by: TaskTurn["by"];
  at: string;
  text: string;
  steered?: boolean;
  files?: ReactNode;
}) {
  const t = useT();
  const me = useMe();
  return (
    <div
      className={cn("ml-auto grid min-w-0 justify-items-end", steered ? "max-w-[80%] gap-1" : "max-w-[88%] gap-1.5")}
    >
      <p className="flex flex-wrap items-center justify-end gap-x-2 text-meta text-ink-muted">
        {by ? <Avatar name={by.name} size="sm" /> : null}
        <span>{by?.name ?? me.assistant}</span>
        <time dateTime={at} className="tabular">
          {hourMinute(at)}
        </time>
        {steered ? (
          <span className="flex items-center gap-1 text-kind-task">
            <CornerDownRight className="size-3.5" aria-hidden="true" />
            {t("task-steered")}
          </span>
        ) : null}
      </p>
      <p
        className={cn(
          "min-w-0 text-body whitespace-pre-line text-ink",
          steered
            ? "rounded-2xl rounded-tr-md border border-dashed border-rule-strong px-3.5 py-2"
            : "rounded-3xl rounded-tr-md bg-paper-sunken px-4 py-2.5",
        )}
      >
        {text}
      </p>
      {files}
    </div>
  );
}

/** The executor's side of a turn as it works: its state, how long it took, its steps. */
function Work({ task, turn }: { task: TaskThread; turn: TaskTurn }) {
  const t = useT();
  const running = turn.status === "running";
  const took = turn.ended_at === null ? null : (Date.parse(turn.ended_at) - Date.parse(turn.started_at)) / 1000;
  return (
    <div className="grid min-w-0 max-w-[88%] gap-3">
      <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-ink-muted">
        <KindName kind={task.executor} className="font-medium text-ink" />
        <span className={cn(running && "text-ember", turn.status === "failed" && "text-brick")}>
          {turnStatusLabel(turn.status)}
        </span>
        {took !== null ? <span className="tabular">{duration(took)}</span> : null}
      </p>
      {turn.steps.length ? <Steps steps={turn.steps} live={running} className="-mb-3" /> : null}
      {running && !turn.steps.length ? <p className="text-body text-ink-muted">{t("task-starting")}</p> : null}
    </div>
  );
}

/** How the turn ended: its report, its question or its failure, the files it handed back, how they reached their
 * person. */
function Outcome({ task, turn }: { task: TaskThread; turn: TaskTurn }) {
  const t = useT();
  const handed = turn.files.filter((f) => !f.given);
  // while it works, the thread that moves comes last, under any instruction it took meanwhile
  if (turn.status === "running") return <span className="thread block max-w-[88%]" aria-hidden="true" />;
  return (
    <div className="grid min-w-0 max-w-[88%] gap-3">
      {turn.result ? <p className="min-w-0 text-body whitespace-pre-line text-ink">{turn.result}</p> : null}
      {turn.question ? <Question text={turn.question} /> : null}
      {turn.error ? (
        <p className="flex items-start gap-2.5 rounded-xl bg-brick-soft px-3.5 py-2.5 text-body text-brick">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 whitespace-pre-line">{turn.error}</span>
        </p>
      ) : null}
      {turn.status === "stopped" && !turn.result ? (
        <p className="text-body text-ink-muted">{t("task-turn-stopped")}</p>
      ) : null}
      {turn.status === "completed" && !turn.result && !handed.length ? (
        <p className="text-body text-ink-muted">{t("task-turn-empty")}</p>
      ) : null}
      <TurnFiles task={task} turn={turn} files={handed} />
      {turn.delivered ? (
        <p className="text-meta text-ink-muted">
          {t("task-delivered", {
            spoken: turn.delivered.channel === "voice" ? "yes" : "no",
            channel: kindName(turn.delivered.channel),
            room: turn.delivered.room ?? "none",
          })}{" "}
          <Ago iso={turn.delivered.at} />
        </p>
      ) : null}
    </div>
  );
}

function TurnFiles({
  task,
  turn,
  files,
  className,
}: {
  task: TaskThread;
  turn: TaskTurn;
  files: TaskFile[];
  className?: string;
}) {
  return <Files files={files} url={fileUrl(task.id, turn.id)} className={className} />;
}

/** What the executor kept for the task as it worked: read again by the agent, never a memory of a person. */
export function Notes({ notes }: { notes: readonly string[] }) {
  const t = useT();
  if (!notes.length) return null;
  return (
    <section aria-label={t("task-notes")} className="grid gap-2.5">
      <h3 className="flex items-center gap-2 title-sub text-ink">
        <NotebookPen className="size-4 text-ink-muted" aria-hidden="true" />
        {t("task-notes")}
      </h3>
      <ul className="grid gap-2">
        {notes.map((note, index) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: notes are an append-only list of plain strings
          <li key={index} className="min-w-0 rounded-xl bg-paper-sunken px-3.5 py-2.5 text-body text-ink">
            {note}
          </li>
        ))}
      </ul>
    </section>
  );
}
