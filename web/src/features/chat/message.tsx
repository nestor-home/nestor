/**
 * The pieces of a chat, after the primitives of agentic chat interfaces (AI Elements): a person's message in a
 * bubble, the assistant's answer as Markdown that renders while it streams, each tool call as a row that opens on
 * its arguments and result, a note when Nestor comes back by itself, and the files of a message.
 */
import { AlertCircle, Check, ChevronRight, Copy, FileText, LoaderCircle, Wrench } from "lucide-react";
import { memo, type ReactNode, useMemo } from "react";
import { Streamdown, type StreamdownTranslations } from "streamdown";
import type { ChatFile, ChatTool, Mention } from "@/api";
import { useCopy } from "@/components/copy-field";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { attachmentUrl } from "@/features/journal/attachments";
import { useT } from "@/i18n";
import { duration, fileSize } from "@/lib/time";
import { cn } from "@/lib/utils";
import { MentionText } from "./mentions";

/** How what has just been written comes in: rising a little, fading in; still under reduced motion. */
export const ARRIVES = "animate-in fade-in-0 slide-in-from-bottom-2 duration-300 ease-out motion-reduce:animate-none";

export function PersonMessage({
  text,
  files,
  mentions,
  pending,
}: {
  text: string;
  files: ReactNode;
  mentions: Mention[];
  pending?: boolean;
}) {
  return (
    <div
      className={cn(
        "ml-auto flex max-w-[85%] flex-col items-end gap-2 transition-opacity duration-300",
        pending && cn(ARRIVES, "opacity-70"),
      )}
    >
      {files}
      {text ? (
        <div className="rounded-2xl rounded-br-md bg-paper-sunken px-4 py-2.5 text-[0.95rem] leading-relaxed whitespace-pre-wrap text-ink [overflow-wrap:anywhere]">
          <MentionText text={text} mentions={mentions} />
        </div>
      ) : null}
    </div>
  );
}

/** The assistant's words: Markdown, rendered as it streams (an unclosed list or code block shows as it will be). */
export const Answer = memo(function Answer({ text, streaming }: { text: string; streaming?: boolean }) {
  const translations = useTranslations();
  return (
    <Streamdown
      className="chat-markdown min-w-0 text-[0.95rem] leading-7 text-ink [overflow-wrap:anywhere]"
      isAnimating={streaming}
      animated={streaming ? { animation: "fadeIn", duration: 220 } : false}
      caret={streaming ? "block" : undefined}
      controls={{ code: true, table: true, mermaid: false }}
      translations={translations}
    >
      {text}
    </Streamdown>
  );
});

function useTranslations(): Partial<StreamdownTranslations> {
  const t = useT();
  return useMemo(
    () => ({
      close: t("chat-md-close"),
      copied: t("action-copied"),
      copyCode: t("chat-md-copy-code"),
      copyLink: t("chat-md-copy-link"),
      copyTable: t("chat-md-copy-table"),
      copyTableAsCsv: t("chat-md-copy-as", { format: "CSV" }),
      copyTableAsMarkdown: t("chat-md-copy-as", { format: "Markdown" }),
      copyTableAsTsv: t("chat-md-copy-as", { format: "TSV" }),
      downloadFile: t("chat-md-download"),
      downloadImage: t("chat-md-download"),
      downloadTable: t("chat-md-download"),
      downloadTableAsCsv: t("chat-md-download-as", { format: "CSV" }),
      downloadTableAsMarkdown: t("chat-md-download-as", { format: "Markdown" }),
      externalLinkWarning: t("chat-md-external-link"),
      imageNotAvailable: t("chat-md-image-missing"),
      openExternalLink: t("chat-md-open-link"),
      openLink: t("chat-md-open-link"),
    }),
    [t],
  );
}

/** Copy, and when the answer was stopped, say so; shown under a finished answer. */
export function AnswerActions({ text, interrupted }: { text: string; interrupted: boolean }) {
  const t = useT();
  const { copied, copy } = useCopy(text);
  return (
    <div className="flex items-center gap-1 text-ink-faint opacity-100 transition-opacity md:opacity-0 md:group-hover/answer:opacity-100 md:group-focus-within/answer:opacity-100">
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => void copy()}
              aria-label={t(copied ? "action-copied" : "action-copy")}
            />
          }
        >
          {copied ? <Check /> : <Copy />}
        </TooltipTrigger>
        <TooltipContent>{t(copied ? "action-copied" : "action-copy")}</TooltipContent>
      </Tooltip>
      {interrupted ? <span className="text-[0.8rem] text-ink-muted">{t("chat-stopped")}</span> : null}
    </div>
  );
}

const TOOL_STATE: Record<ChatTool["state"], { icon: ReactNode; tone: string }> = {
  running: { icon: <LoaderCircle className="size-3.5 animate-spin" />, tone: "text-ink-muted" },
  done: { icon: <Check className="size-3.5" />, tone: "text-sage" },
  failed: { icon: <AlertCircle className="size-3.5" />, tone: "text-brick" },
  background: { icon: <LoaderCircle className="size-3.5 animate-spin" />, tone: "text-amber" },
};

/** A tool call: its name and how it stands; opened, what it was given and what came back. */
export function ToolCall({ tool }: { tool: ChatTool }) {
  const t = useT();
  const state = TOOL_STATE[tool.state];
  const args = Object.keys(tool.arguments).length ? JSON.stringify(tool.arguments, null, 2) : null;
  return (
    <Collapsible className="group/tool w-full rounded-lg border border-rule bg-paper-raised/60 text-[0.85rem]">
      <CollapsibleTrigger className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left outline-none hover:bg-paper-sunken/60 focus-visible:outline-2 focus-visible:outline-ember">
        <Wrench className="size-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
        <span className="min-w-0 truncate font-mono text-[0.8rem] text-ink">{tool.name}</span>
        <span className={cn("ml-auto flex shrink-0 items-center gap-1.5 transition-colors", state.tone)}>
          <span key={tool.state} className="animate-in duration-200 zoom-in-50 fade-in-0 motion-reduce:animate-none">
            {state.icon}
          </span>
          <span>
            {tool.state === "done" && tool.duration_s !== null
              ? t("chat-tool-done-in", { duration: duration(tool.duration_s) })
              : t(`chat-tool-${tool.state}`)}
          </span>
        </span>
        <ChevronRight
          className="size-3.5 shrink-0 text-ink-faint transition-transform in-data-panel-open:rotate-90"
          aria-hidden="true"
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="h-(--collapsible-panel-height) overflow-hidden transition-[height] duration-200 ease-out data-ending-style:h-0 data-starting-style:h-0 motion-reduce:transition-none">
        <div className="grid gap-3 border-t border-rule px-3 py-3">
          {args ? <ToolBlock label={t("chat-tool-arguments")}>{args}</ToolBlock> : null}
          {tool.output !== null ? (
            <ToolBlock label={t("chat-tool-result")}>{tool.output || t("chat-tool-empty")}</ToolBlock>
          ) : (
            <p className="text-ink-muted">{t("chat-tool-waiting")}</p>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function ToolBlock({ label, children }: { label: string; children: string }) {
  return (
    <div className="grid gap-1.5">
      <p className="label-mono text-[0.68rem] text-ink-faint">{label}</p>
      <pre className="max-h-64 overflow-auto rounded-md bg-paper-sunken px-3 py-2 font-mono text-[0.78rem] leading-relaxed whitespace-pre-wrap text-ink [overflow-wrap:anywhere]">
        {children}
      </pre>
    </div>
  );
}

/** What Nestor brought in by itself (a task's result, a reminder), before its answer. */
export function Note({ text, assistant }: { text: string; assistant: string }) {
  const t = useT();
  return (
    <div className="flex items-center gap-3 text-[0.8rem] text-ink-muted" role="note">
      <span className="h-px flex-1 bg-rule" aria-hidden="true" />
      <span className="flex items-center gap-1.5">
        <span className="size-1.5 rounded-full bg-ember" aria-hidden="true" />
        {t("chat-note", { assistant, about: text })}
      </span>
      <span className="h-px flex-1 bg-rule" aria-hidden="true" />
    </div>
  );
}

export function Fallback({ text }: { text: string }) {
  return (
    <p className="flex items-start gap-2 text-[0.9rem] text-brick">
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      {text}
    </p>
  );
}

/** The files of a message: pictures shown, recordings playable with what was said, other files to download. */
export function Files({ files, align = "start" }: { files: ChatFile[]; align?: "start" | "end" }) {
  const t = useT();
  if (!files.length) return null;
  return (
    <ul className={cn("flex max-w-full flex-wrap gap-2", align === "end" && "justify-end")}>
      {files.map((file) => {
        const url = attachmentUrl(file.position, file.index);
        const name = file.name ?? t(`chat-file-${file.kind}`);
        return (
          <li key={`${file.position}-${file.index}`} className="min-w-0 max-w-full">
            {file.kind === "image" ? (
              <a href={url} target="_blank" rel="noreferrer" className="block">
                <img
                  src={url}
                  alt={name}
                  loading="lazy"
                  className="max-h-64 max-w-full rounded-xl border border-rule object-contain"
                />
              </a>
            ) : file.kind === "voice" || file.kind === "audio" ? (
              <Recording url={url} name={file.kind === "voice" ? null : name} transcript={file.transcript} />
            ) : (
              <a
                href={url}
                download={file.name ?? true}
                className="flex max-w-xs items-center gap-2.5 rounded-xl border border-rule bg-paper-raised px-3 py-2.5 text-sm text-ink hover:border-ink"
              >
                <FileText className="size-5 shrink-0 text-ink-muted" aria-hidden="true" />
                <span className="min-w-0">
                  <span className="block truncate">{name}</span>
                  <span className="block font-mono text-xs text-ink-muted">{fileSize(file.size)}</span>
                </span>
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Recording({ url, name, transcript }: { url: string; name: string | null; transcript: string | null }) {
  const t = useT();
  return (
    <div className="grid w-80 max-w-full gap-1.5 rounded-xl border border-rule bg-paper-raised p-2.5">
      {name ? <p className="truncate px-1 text-[0.82rem] text-ink-muted">{name}</p> : null}
      <audio controls preload="metadata" src={url} className="h-9 w-full">
        <track kind="captions" />
      </audio>
      {transcript ? (
        <details className="px-1 text-[0.85rem] text-ink-muted">
          <summary className="cursor-pointer select-none text-ink-faint">{t("chat-transcript")}</summary>
          <p className="mt-1 [overflow-wrap:anywhere]">{transcript}</p>
        </details>
      ) : null}
    </div>
  );
}
