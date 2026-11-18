/**
 * What every place that shows a watch shares: the mark of what it watches and the way to cancel it. Kept apart
 * from the watch's page so that Ongoing does not load it.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api, keys, type Watch } from "@/api";
import { Confirm } from "@/components/confirm";
import { useNotify } from "@/components/notices";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { BrandMark, type BrandSlug, brandOf } from "@/lib/brands";
import { useCan } from "@/lib/session";

/** The mark of what a watch watches: the kinds Nestor's sources bring, else a brand (a webhook named `github`). */
const KIND_MARKS: Record<string, BrandSlug> = { mail: "email", feed: "rss", page: "web-page" };

/** The brand that stands for a kind of watch. */
export const watchBrand = (kind: string | undefined): BrandSlug =>
  (kind && (KIND_MARKS[kind] ?? brandOf(kind))) || "webhook";

/** What a watch watches ("mail", "feed", a webhook's kind), with its mark. */
export function WatchKind({ kind }: { kind: string }) {
  const t = useT();
  return (
    <span className="inline-flex items-center gap-1.5">
      <BrandMark brand={watchBrand(kind)} className="size-3.5" label={false} />
      {t("watch-kind", { kind })}
    </span>
  );
}

/** The way to cancel a watch, behind its confirmation, for whoever may; `onDone` once it is cancelled. */
export function CancelWatch({ watch, onDone }: { watch: Watch; onDone?: () => void }) {
  const t = useT();
  const allowed = useCan("watches:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelWatch(watch.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.watches });
      notify(t("watch-cancelled-notice"));
      onDone?.();
    },
  });
  if (!allowed) return null;
  return (
    <Confirm
      trigger={
        <Button variant="destructive">
          <Trash2 /> {t("watch-cancel-action")}
        </Button>
      }
      title={t("watch-cancel-title")}
      confirm={t("watch-cancel")}
      onConfirm={() => cancel.mutateAsync()}
    >
      {t("watch-cancel-description", { what: watch.title })}
    </Confirm>
  );
}
