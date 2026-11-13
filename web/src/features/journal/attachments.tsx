import { FileText, Mic } from "lucide-react";
import type { AttachmentKind, JournalItem } from "@/api";
import { API_BASE } from "@/api/client";
import { useT } from "@/i18n";
import { is } from "@/lib/events";
import { fileSize } from "@/lib/time";
import { cn } from "@/lib/utils";

/** Where the server serves a file of the journal's entry at `position`, to whoever reads the entry. */
export const attachmentUrl = (position: number, index: number) =>
  `${API_BASE}/journal/${position}/attachments/${index}`;

interface File {
  index: number;
  kind: AttachmentKind;
  size: number;
  name?: string | null;
  transcript?: string | null;
}

/** The files of a journal entry: what a person sent, or what a tool, a task or an answer made. */
export function Attachments({ item, className }: { item: JournalItem; className?: string }) {
  return (
    <Files
      files={item.attachments}
      url={(index) => attachmentUrl(item.position, index)}
      sent={is(item, "userTurn")}
      className={className}
    />
  );
}

/**
 * Files, each where it is served: pictures shown, recordings playable, other files to download.
 * `sent`: a person sent them, so a voice message that could not be transcribed says so.
 */
export function Files({
  files,
  url: urlOf,
  sent = false,
  className,
}: {
  files: readonly File[];
  url: (index: number) => string;
  sent?: boolean;
  className?: string;
}) {
  const t = useT();
  if (!files.length) return null;
  return (
    <ul className={cn("grid max-w-full gap-2", className)}>
      {files.map((attachment) => {
        const url = urlOf(attachment.index);
        const name = attachment.name ?? t(`jr-attachment-${attachment.kind}`);
        return (
          <li key={attachment.index} className="min-w-0">
            {attachment.kind === "image" ? (
              <a href={url} target="_blank" rel="noreferrer" className="block w-fit">
                <img
                  src={url}
                  alt={name}
                  loading="lazy"
                  className="max-h-56 max-w-full rounded-lg border border-rule object-contain"
                />
              </a>
            ) : attachment.kind === "voice" || attachment.kind === "audio" ? (
              <div className="grid gap-1">
                <p className="flex items-center gap-1.5 text-[0.82rem] text-ink-muted">
                  <Mic className="size-3.5" aria-hidden="true" />
                  <span className="truncate">{name}</span>
                  {sent && attachment.kind === "voice" && !attachment.transcript ? (
                    <span>· {t("jr-attachment-unheard")}</span>
                  ) : null}
                </p>
                <audio controls preload="none" src={url} className="h-9 w-72 max-w-full">
                  <track kind="captions" />
                </audio>
                {attachment.kind === "audio" && attachment.transcript ? (
                  <p className="text-[0.88rem] text-ink-muted [overflow-wrap:anywhere]">{attachment.transcript}</p>
                ) : null}
              </div>
            ) : (
              <a
                href={url}
                download={attachment.name ?? true}
                className="inline-flex max-w-full items-center gap-2 rounded-md border border-rule px-3 py-2 text-sm text-ink hover:border-ink"
              >
                <FileText className="size-4 shrink-0 text-ink-muted" aria-hidden="true" />
                <span className="truncate">{name}</span>
                <span className="shrink-0 font-mono text-xs text-ink-muted">{fileSize(attachment.size)}</span>
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}
