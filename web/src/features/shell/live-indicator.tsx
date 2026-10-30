import { Status } from "@/components/status";
import { useT } from "@/i18n";
import { useLive } from "./live";

const SAID = { open: "shell-live-open", connecting: "shell-live-connecting", closed: "shell-live-closed" } as const;

/** The live stream's state; `compact` keeps the dot, the words go to the tooltip and the label. */
export function LiveIndicator({ compact = false }: { compact?: boolean }) {
  const t = useT();
  const { status } = useLive();
  if (compact) {
    return (
      <span
        role="img"
        aria-label={t(SAID[status])}
        title={`${t(SAID[status])} · ${t("shell-live-hint")}`}
        className="grid size-9 place-items-center"
      >
        <span
          aria-hidden="true"
          className={
            status === "open"
              ? "live-dot size-2 rounded-full bg-ember"
              : status === "connecting"
                ? "size-2 rounded-full bg-amber"
                : "size-2 rounded-full border border-ink-faint"
          }
        />
      </span>
    );
  }
  return (
    <span title={t("shell-live-hint")}>
      <Status tone={status === "open" ? "accent" : status === "connecting" ? "attention" : "idle"}>
        <span className={status === "open" ? "live-dot" : undefined}>{t(SAID[status])}</span>
      </Status>
    </span>
  );
}
