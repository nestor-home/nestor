/**
 * What every place that shows an alert shares: its mark, what rings it in words, why it last rang and the way to
 * cancel it. Kept apart from the alert's page so that Ongoing does not load it.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlarmClock, Repeat, Trash2 } from "lucide-react";
import { type Alert, api, keys, type Ring } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { BrandTile, IconTile, type TileSize } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { BrandMark, type BrandSlug, brandOf } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { rangBecause, weekdayLabel } from "@/lib/labels";
import { useCan } from "@/lib/session";

/** The mark of what items ring an alert: the kinds Nestor's sources bring, else a brand (a webhook named `github`). */
const KIND_MARKS: Record<string, BrandSlug> = { mail: "email", feed: "rss", page: "web-page" };

/** The brand that stands for a kind of item. */
export const kindBrand = (kind: string | undefined): BrandSlug =>
  (kind && (KIND_MARKS[kind] ?? brandOf(kind))) || "webhook";

/** An alert's mark: the source it waits for, or a clock for one that rings at times. */
export function AlertMark({ alert, size }: { alert: Alert; size?: TileSize }) {
  if (alert.trigger === "events") return <BrandTile brand={kindBrand(alert.kinds[0])} size={size} />;
  return <IconTile icon={alert.trigger === "times" ? Repeat : AlarmClock} tone="alert" size={size} />;
}

/** A kind of item an alert waits for ("mail", "feed", a webhook's kind), with its mark. */
export function AlertKind({ kind }: { kind: string }) {
  const t = useT();
  return (
    <span className="inline-flex items-center gap-1.5">
      <BrandMark brand={kindBrand(kind)} className="size-3.5" label={false} />
      {t("alert-kind", { kind })}
    </span>
  );
}

/** What rings it, in words: once at a moment, its days and times, or the kinds of items it waits for. */
export function rings(alert: Alert): string {
  if (alert.trigger === "at") return tr("alert-once-at", { when: alert.at ? moment(alert.at) : "" });
  if (alert.trigger === "times") {
    const days = alert.days.length ? alert.days.map(weekdayLabel).join(", ") : tr("alert-every-day");
    return `${days} · ${alert.times.join(", ")}`;
  }
  return tr("alert-on-kinds", { kinds: alert.kinds.map((kind) => tr("alert-kind", { kind })).join(", ") });
}

/** Why it rang, and when: "Its time came · 2 h ago". */
export function RangBecause({ ring }: { ring: Ring }) {
  return (
    <span>
      {rangBecause(ring)}
      {ring.summary && ring.cause === "match" ? <span className="text-ink-muted">{` · ${ring.summary}`}</span> : null}
      <span className="text-ink-muted">
        {" · "}
        <Ago iso={ring.at} />
      </span>
    </span>
  );
}

/** The way to cancel an alert, behind its confirmation, for whoever may; `onDone` once it is cancelled. */
export function CancelAlert({ alert, onDone }: { alert: Alert; onDone?: () => void }) {
  const t = useT();
  const allowed = useCan("alerts:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelAlert(alert.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.alerts });
      notify(t("alert-cancelled-notice"));
      onDone?.();
    },
  });
  if (!allowed) return null;
  return (
    <Confirm
      trigger={
        <Button variant="destructive">
          <Trash2 /> {t("alert-cancel-action")}
        </Button>
      }
      title={t("alert-cancel-title")}
      confirm={t("alert-cancel")}
      onConfirm={() => cancel.mutateAsync()}
    >
      {t("alert-cancel-description", { what: alert.title })}
    </Confirm>
  );
}
