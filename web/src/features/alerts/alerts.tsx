/**
 * An alert on its page: what rings it and for whom, how often it tells, why it rang each time, then what it went
 * through as the journal tells it.
 */
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { BellRing, Repeat } from "lucide-react";
import { type Alert, alertQuery, isMissing } from "@/api";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { Avatar, IconTile } from "@/components/marks";
import { OriginLink } from "@/components/origin-link";
import { PageHeader, RowList, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { SubjectStory } from "@/features/journal/subject-story";
import { useT } from "@/i18n";
import { moment } from "@/lib/dates";
import { personName } from "@/lib/people";
import { AlertFrequency, AlertMark, CancelAlert, RangBecause, rings } from "./parts";

export function AlertDetail({ id }: { id: string }) {
  const t = useT();
  const found = useQuery(alertQuery(id));
  const trail: Crumb[] = [
    { label: t("space-activity"), link: { to: "/activity" } },
    { label: found.data?.title ?? id },
  ];
  if (found.isPending) return <Loading lines={4} />;
  const alert = found.data;
  if (!alert) {
    return (
      <>
        <Crumbs trail={trail} />
        {isMissing(found.error) ? <Empty>{t("alert-unknown")}</Empty> : <Failure error={found.error} />}
      </>
    );
  }
  return <Loaded alert={alert} trail={trail} />;
}

function Loaded({ alert: a, trail }: { alert: Alert; trail: Crumb[] }) {
  const t = useT();
  const navigate = useNavigate();
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={a.title}
        meta={
          <>
            {a.owner ? <Avatar name={a.owner.name} size="sm" /> : null}
            <span>{t("alert-for", { name: personName(a.owner) })}</span>
            <span>{t("alert-created", { when: moment(a.created_at) })}</span>
            {a.until ? <span>{t("alert-until", { when: moment(a.until) })}</span> : null}
          </>
        }
        actions={<CancelAlert alert={a} onDone={() => void navigate({ to: "/activity" })} />}
      >
        {a.instruction}
      </PageHeader>
      <div className="grid gap-10">
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="surface flex flex-col gap-3 p-4">
              <p className="text-body font-medium text-ink-muted">{t("alert-trigger")}</p>
              <p className="mt-auto flex items-center gap-3 font-medium text-ink">
                <AlertMark alert={a} size="sm" />
                <span className="min-w-0">{rings(a)}</span>
              </p>
            </div>
            <div className="surface flex flex-col gap-3 p-4">
              <p className="text-body font-medium text-ink-muted">{t("alert-frequency-term")}</p>
              <p className="mt-auto flex items-center gap-3 text-ink">
                <IconTile icon={Repeat} size="sm" />
                <span className="min-w-0">
                  <AlertFrequency alert={a} />
                </span>
              </p>
            </div>
            <div className="surface flex flex-col gap-3 p-4">
              <p className="text-body font-medium text-ink-muted">{t("alert-so-far")}</p>
              <p className="mt-auto flex items-center gap-3">
                <IconTile icon={BellRing} tone={a.rang ? "ember" : "alert"} size="sm" />
                <span className={a.rang ? "font-medium text-ink" : "text-ink-muted"}>
                  {a.rang ? t("alert-rang-count", { count: a.rang }) : t("alert-never-rang")}
                </span>
              </p>
            </div>
          </div>
          {a.condition ? (
            <p className="text-body text-ink">
              <span className="text-ink-muted">{t("alert-condition")} </span>
              {a.condition}
            </p>
          ) : null}
          {a.origin ? (
            <p className="text-body text-ink-muted first-letter:uppercase">
              {t("alert-asked-in")} <OriginLink origin={a.origin} />
            </p>
          ) : null}
        </div>
        <Section title={t("alert-rings")} count={a.rang}>
          {a.rings.length ? (
            <RowList>
              {a.rings.map((ring) => (
                <li key={ring.id} className="px-4 py-3 text-body text-ink">
                  <RangBecause ring={ring} />
                </li>
              ))}
            </RowList>
          ) : (
            <Empty>{t("alert-rings-empty")}</Empty>
          )}
        </Section>
        <Section title={t("alert-found")}>
          <SubjectStory filters={{ alert: a.id }} empty={t("alert-found-empty")} />
        </Section>
      </div>
    </>
  );
}
