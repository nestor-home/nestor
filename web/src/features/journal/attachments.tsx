import { FileText, Mic } from "lucide-react";
import type { JournalItem } from "@/api";
import { API_BASE } from "@/api/client";
import { activeLocale, useT } from "@/i18n";
import { cn } from "@/lib/utils";

type Attachment = JournalItem["attachments"][number];

/** Where the server serves a file sent with a message, to whoever reads its entry. */
export const attachmentUrl = (item: JournalItem, attachment: Attachment) =>
  `${API_BASE}/journal/${item.position}/attachments/${attachment.index}`;

/** The files a person sent with a message: pictures shown, recordings playable, other files to download. */
export function Attachments({ item, className }: { item: JournalItem; className?: string }) {
  const t = useT();
  if (!item.attachments.length) return null;
  return (
    <ul className={cn("grid max-w-full gap-2", className)}>
      {item.attachments.map((attachment) => {
        const url = attachmentUrl(item, attachment);
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
                  {attachment.kind === "voice" && attachment.transcript === null ? (
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

function fileSize(bytes: number): string {
  const [value, unit] =
    bytes >= 1_000_000
      ? [bytes / 1_000_000, "megabyte"]
      : bytes >= 1_000
        ? [bytes / 1_000, "kilobyte"]
        : [bytes, "byte"];
  return new Intl.NumberFormat(activeLocale(), { style: "unit", unit, maximumFractionDigits: 1 }).format(value);
}
