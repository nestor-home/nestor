/**
 * A watch on its page: what it keeps an eye on and for whom, how often it reports, what it found so far,
 * then each thing it found as the journal tells it.
 */
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Radar, Repeat } from "lucide-react";
import { isMissing, type Watch, watchQuery } from "@/api";
import { Ago } from "@/components/ago";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { BrandTile, IconTile, Pebble } from "@/components/marks";
import { OriginLink } from "@/components/origin-link";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { SubjectStory } from "@/features/journal/subject-story";
import { useT } from "@/i18n";
import { moment } from "@/lib/dates";
import { personName } from "@/lib/people";
import { CancelWatch, watchBrand } from "./parts";

export function WatchDetail({ id }: { id: string }) {
  const t = useT();
  const found = useQuery(watchQuery(id));
  const trail: Crumb[] = [
    { label: t("space-activity"), link: { to: "/activity" } },
    { label: found.data?.title ?? id },
  ];
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
  const navigate = useNavigate();
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={w.title}
        meta={
          <>
            {w.owner ? <Pebble name={w.owner.name} size="sm" /> : null}
            <span>{t("watch-for", { name: personName(w.owner) })}</span>
            <span>{t("watch-created", { when: moment(w.created_at) })}</span>
            {w.until ? <span>{t("watch-until", { when: moment(w.until) })}</span> : null}
          </>
        }
        actions={<CancelWatch watch={w} onDone={() => void navigate({ to: "/activity" })} />}
      >
        {w.what}
      </PageHeader>
      <div className="grid gap-10">
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="surface flex flex-col gap-3 p-4">
              <p className="text-body font-medium text-ink-muted">{t("watch-watches")}</p>
              <ul className="mt-auto grid gap-2">
                {w.kinds.map((k) => (
                  <li key={k} className="flex items-center gap-3 font-medium text-ink">
                    <BrandTile brand={watchBrand(k)} size="sm" />
                    {t("watch-kind", { kind: k })}
                  </li>
                ))}
              </ul>
            </div>
            <div className="surface flex flex-col gap-3 p-4">
              <p className="text-body font-medium text-ink-muted">{t("watch-rhythm")}</p>
              <p className="mt-auto flex items-center gap-3 text-ink">
                <IconTile icon={Repeat} size="sm" />
                {w.once ? t("watch-rhythm-once") : t("watch-rhythm-every")}
              </p>
            </div>
            <div className="surface flex flex-col gap-3 p-4">
              <p className="text-body font-medium text-ink-muted">{t("watch-so-far")}</p>
              <p className="mt-auto flex items-center gap-3">
                <IconTile icon={Radar} tone={w.triggered ? "ember" : "watch"} size="sm" />
                <span className="min-w-0">
                  <span className={w.triggered ? "block font-medium text-ink" : "block text-ink-muted"}>
                    {w.triggered ? t("watch-triggered-count", { count: w.triggered }) : t("watch-never-triggered")}
                  </span>
                  {w.last_triggered_at ? (
                    <span className="block text-meta text-ink-muted">
                      {t("watch-last")} <Ago iso={w.last_triggered_at} />
                    </span>
                  ) : null}
                </span>
              </p>
            </div>
          </div>
          {w.origin ? (
            <p className="text-body text-ink-muted first-letter:uppercase">
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
