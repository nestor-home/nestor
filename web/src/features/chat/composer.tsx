/**
 * Where a message is written: the text grows with it, files come by the clip, a drop or a paste, a voice message is
 * recorded in place. Enter sends, Shift+Enter goes to the line; while the answer is written, the send button stops
 * it. The draft of each chat is kept in the browser until it is sent.
 */

import { useQuery } from "@tanstack/react-query";
import { ArrowUp, AtSign, FileText, Mic, Paperclip, Square, Trash2, X } from "lucide-react";
import { type ReactElement, type Ref, useEffect, useImperativeHandle, useRef, useState } from "react";
import { toast } from "sonner";
import { type ChatMessageIn, mentionsQuery } from "@/api";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useT } from "@/i18n";
import { fileSize } from "@/lib/time";
import { ChatEditor, type EditorHandle } from "./editor";
import { FILE_LIMIT, FILES_PER_MESSAGE, kindOf, type PendingFile, pending } from "./files";
import { useRecorder } from "./recorder";

const DRAFTS = "nestor.chat.draft.";

function readDraft(key: string): string {
  try {
    return localStorage.getItem(DRAFTS + key) ?? "";
  } catch {
    return "";
  }
}

function keepDraft(key: string, text: string): void {
  try {
    if (text) localStorage.setItem(DRAFTS + key, text);
    else localStorage.removeItem(DRAFTS + key);
  } catch {
    // a private window: the draft lives as long as the page
  }
}

export interface ComposerHandle {
  add: (files: Iterable<File>) => void;
}

export function Composer({
  draftKey,
  assistant,
  answering,
  onSend,
  onStop,
  ref,
}: {
  draftKey: string;
  assistant: string;
  answering: boolean;
  onSend: (message: ChatMessageIn) => Promise<boolean>; // false: refused, keep what was written
  onStop: () => void;
  ref?: Ref<ComposerHandle>;
}) {
  const t = useT();
  const [text, setText] = useState(() => readDraft(draftKey));
  const [files, setFiles] = useState<PendingFile[]>([]);
  const [sending, setSending] = useState(false);
  const input = useRef<EditorHandle>(null);
  const { data: mentions = [] } = useQuery(mentionsQuery);
  const picker = useRef<HTMLInputElement>(null);
  const recorder = useRecorder();
  const recording = recorder.status.state === "recording" ? recorder.status : null;

  useEffect(() => keepDraft(draftKey, text), [draftKey, text]);
  useEffect(() => {
    if (recorder.status.state === "refused") toast.error(t("chat-mic-refused"));
  }, [recorder.status.state, t]);

  const add = async (picked: Iterable<File>) => {
    const chosen = [...picked];
    const tooLarge = chosen.filter((file) => file.size > FILE_LIMIT);
    if (tooLarge.length)
      toast.error(t("chat-file-too-large", { name: tooLarge[0]?.name ?? "", limit: fileSize(FILE_LIMIT) }));
    const kept = chosen.filter((file) => file.size > 0 && file.size <= FILE_LIMIT);
    const read = await Promise.all(kept.map((file) => pending(file, kindOf(file.type), file.name)));
    setFiles((current) => {
      const all = [...current, ...read];
      if (all.length > FILES_PER_MESSAGE) toast.error(t("chat-too-many-files", { count: FILES_PER_MESSAGE }));
      return all.slice(0, FILES_PER_MESSAGE);
    });
    input.current?.focus();
  };

  useImperativeHandle(ref, () => ({ add: (picked) => void add(picked) }));

  const submit = async (voice?: PendingFile) => {
    const words = input.current?.text().trim() ?? "";
    const all = voice ? [...files, voice] : files;
    if (answering || sending || !(words || all.length)) return;
    setSending(true);
    const sent = await onSend({ text: words, files: all.map((f) => f.file) });
    setSending(false);
    if (sent) {
      input.current?.clear();
      setText("");
      setFiles([]);
    }
    input.current?.focus();
  };

  const finishRecording = async () => {
    const blob = await recorder.finish();
    if (blob) await submit(await pending(blob, "voice", null));
  };

  const empty = !(text.trim() || files.length);

  return (
    <div className="relative rounded-2xl border border-rule-strong bg-paper-raised shadow-[0_1px_0_var(--rule)] transition-[border-color,box-shadow] duration-200 focus-within:border-ink focus-within:shadow-[0_6px_24px_-12px_var(--rule-strong)]">
      {files.length ? (
        <ul className="flex flex-wrap gap-2 px-3 pt-3" aria-label={t("chat-attached")}>
          {files.map((file) => (
            <li key={file.id} className="group/file relative">
              {file.preview ? (
                <img
                  src={file.preview}
                  alt={file.file.name ?? ""}
                  className="size-16 rounded-lg border border-rule object-cover"
                />
              ) : (
                <span className="flex h-16 max-w-52 items-center gap-2 rounded-lg border border-rule bg-paper px-3">
                  <FileText className="size-5 shrink-0 text-ink-muted" aria-hidden="true" />
                  <span className="min-w-0 text-[0.8rem]">
                    <span className="block truncate text-ink">{file.file.name}</span>
                    <span className="block font-mono text-ink-muted">{fileSize(file.size)}</span>
                  </span>
                </span>
              )}
              <button
                type="button"
                onClick={() => setFiles((current) => current.filter((f) => f.id !== file.id))}
                aria-label={t("chat-remove-file", { name: file.file.name ?? "" })}
                className="absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full border border-rule-strong bg-paper-raised text-ink-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-ember"
              >
                <X className="size-3" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {recording ? (
        <Recording
          seconds={recording.seconds}
          level={recording.level}
          onCancel={recorder.cancel}
          onSend={() => void finishRecording()}
        />
      ) : (
        <>
          <ChatEditor
            ref={input}
            initial={text}
            placeholder={t("chat-placeholder", { assistant })}
            onChange={setText}
            onSubmit={() => void submit()}
            onFiles={(picked) => void add(picked)}
          />
          <div className="flex items-center gap-1 px-2 pb-2">
            <input
              ref={picker}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => {
                if (event.target.files) void add(event.target.files);
                event.target.value = "";
              }}
            />
            <Hint label={t("chat-attach")}>
              <Button variant="ghost" size="icon" onClick={() => picker.current?.click()} aria-label={t("chat-attach")}>
                <Paperclip />
              </Button>
            </Hint>
            {mentions.length ? (
              <Hint label={t("chat-mention")}>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t("chat-mention")}
                  onClick={() => input.current?.mention()}
                >
                  <AtSign />
                </Button>
              </Hint>
            ) : null}
            <div className="ml-auto flex items-center gap-1">
              {empty && !answering ? (
                <Hint label={t("chat-record")}>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => void recorder.start()}
                    aria-label={t("chat-record")}
                  >
                    <Mic />
                  </Button>
                </Hint>
              ) : null}
              {answering ? (
                <Hint label={t("chat-stop")}>
                  <Button size="icon" onClick={onStop} aria-label={t("chat-stop")} className="rounded-full">
                    <Square className="size-3 fill-current" />
                  </Button>
                </Hint>
              ) : (
                <Hint label={t("chat-send")}>
                  <Button
                    variant="accent"
                    size="icon"
                    onClick={() => void submit()}
                    disabled={empty || sending}
                    aria-label={t("chat-send")}
                    className="rounded-full"
                  >
                    <ArrowUp />
                  </Button>
                </Hint>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Recording({
  seconds,
  level,
  onCancel,
  onSend,
}: {
  seconds: number;
  level: number;
  onCancel: () => void;
  onSend: () => void;
}) {
  const t = useT();
  const time = `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
  return (
    <div className="flex items-center gap-3 px-2 py-2" role="status" aria-label={t("chat-recording")}>
      <Hint label={t("chat-record-cancel")}>
        <Button variant="ghost" size="icon" onClick={onCancel} aria-label={t("chat-record-cancel")}>
          <Trash2 />
        </Button>
      </Hint>
      <span className="live-dot size-2 rounded-full bg-ember" aria-hidden="true" />
      <span className="font-mono text-[0.85rem] text-ink tabular-nums">{time}</span>
      <Level level={level} />
      <Hint label={t("chat-record-send")}>
        <Button
          variant="accent"
          size="icon"
          onClick={onSend}
          aria-label={t("chat-record-send")}
          className="rounded-full"
        >
          <ArrowUp />
        </Button>
      </Hint>
    </div>
  );
}

/** How loud it is now, as a row of bars that rise with the voice. */
function Level({ level }: { level: number }) {
  const bars = [0.35, 0.6, 0.85, 1, 0.85, 0.6, 0.35, 0.5, 0.75, 0.5];
  return (
    <span className="flex h-6 flex-1 items-center justify-center gap-1" aria-hidden="true">
      {bars.map((weight, i) => (
        <span
          // biome-ignore lint/suspicious/noArrayIndexKey: a fixed row of bars
          key={i}
          className="w-1 rounded-full bg-ink-muted transition-[height] duration-100"
          style={{ height: `${Math.max(12, Math.min(100, level * weight * 140))}%` }}
        />
      ))}
    </span>
  );
}

function Hint({ label, children }: { label: string; children: ReactElement }) {
  return (
    <Tooltip>
      <TooltipTrigger render={children} />
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
