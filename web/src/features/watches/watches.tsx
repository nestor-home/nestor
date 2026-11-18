/**
 * A watch on its page: what it keeps an eye on and for whom, how often it reports, what it found so far,
 * then each thing it found as the journal tells it.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Radar, Repeat, Trash2 } from "lucide-react";
import { api, isMissing, keys, type Watch, watchQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { BrandTile, IconTile, Pebble } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { OriginLink } from "@/components/origin-link";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { SubjectStory } from "@/features/journal/subject-story";
import { useT } from "@/i18n";
import { BrandMark, type BrandSlug, brandOf } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { personName } from "@/lib/people";
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
    <span className="inline-flex items-center gap-1">
      <BrandMark brand={watchBrand(kind)} className="size-3.5" label={false} />
      {t("watch-kind", { kind })}
    </span>
  );
}

export function WatchDetail({ id }: { id: string }) {
  const t = useT();
  const found = useQuery(watchQuery(id));
  const trail: Crumb[] = [{ label: t("space-activity"), link: { to: "/activity" } }, { label: id }];
  if (found.isPending) return <Loading lines={4} />;
  const watch = found.data;
  if (!watch) {
    return (
      <>
        <Crumbs trail={trail} />
        {isMissing(found.error) ? <Empty>{t("watch-unknown")}</Empty> : <Failure error={found.error} />}
      </>
    );
  }
  return <Loaded watch={watch} trail={trail} />;
}

function Loaded({ watch: w, trail }: { watch: Watch; trail: Crumb[] }) {
  const t = useT();
  const canCancel = useCan("watches:write");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelWatch(w.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.watches });
      notify(t("watch-cancelled-notice"));
      void navigate({ to: "/activity" });
    },
  });
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={w.title}
        meta={
          <>
            {w.owner ? <Pebble name={w.owner.name} className="size-6 text-[0.65rem]" /> : null}
            <span>{t("watch-for", { name: personName(w.owner) })}</span>
            <span>{t("watch-created", { when: moment(w.created_at) })}</span>
            {w.until ? <span>{t("watch-until", { when: moment(w.until) })}</span> : null}
          </>
        }
        actions={
          canCancel ? (
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
              {t("watch-cancel-description", { what: w.title })}
            </Confirm>
          ) : null
        }
      >
        {w.what}
      </PageHeader>
      <div className="grid gap-10">
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="surface flex flex-col gap-3 p-4">
              <p className="text-[0.9rem] font-medium text-ink-muted">{t("watch-watches")}</p>
              <ul className="mt-auto grid gap-2">
                {w.kinds.map((k) => (
                  <li key={k} className="flex items-center gap-3 font-medium text-ink">
                    <BrandTile brand={watchBrand(k)} className="size-9" />
                    {t("watch-kind", { kind: k })}
                  </li>
                ))}
              </ul>
            </div>
            <div className="surface flex flex-col gap-3 p-4">
              <p className="text-[0.9rem] font-medium text-ink-muted">{t("watch-rhythm")}</p>
              <p className="mt-auto flex items-center gap-3 text-ink">
                <IconTile icon={Repeat} className="size-9" />
                {w.once ? t("watch-rhythm-once") : t("watch-rhythm-every")}
              </p>
            </div>
            <div className="surface flex flex-col gap-3 p-4">
              <p className="text-[0.9rem] font-medium text-ink-muted">{t("watch-so-far")}</p>
              <p className="mt-auto flex items-center gap-3">
                <IconTile icon={Radar} tone={w.triggered ? "ember" : "watch"} className="size-9" />
                <span className="min-w-0">
                  <span className={w.triggered ? "block font-medium text-ink" : "block text-ink-muted"}>
                    {w.triggered ? t("watch-triggered-count", { count: w.triggered }) : t("watch-never-triggered")}
                  </span>
                  {w.last_triggered_at ? (
                    <span className="block text-[0.85rem] text-ink-muted">
                      {t("watch-last")} <Ago iso={w.last_triggered_at} />
                    </span>
                  ) : null}
                </span>
              </p>
            </div>
          </div>
          {w.origin ? (
            <p className="text-[0.92rem] text-ink-muted first-letter:uppercase">
              {t("watch-asked-in")} <OriginLink origin={w.origin} />
            </p>
          ) : null}
        </div>
        <Section title={t("watch-found")} count={w.triggered}>
          <SubjectStory filters={{ watch: w.id }} empty={t("watch-found-empty")} />
        </Section>
      </div>
    </>
  );
}
