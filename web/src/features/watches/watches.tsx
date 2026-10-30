import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArrowRight, MessageSquareText } from "lucide-react";
import { api, isMissing, keys, type Watch, watchesQuery, watchQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { useNotify } from "@/components/notices";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Tag } from "@/components/status";
import { Button } from "@/components/ui/button";
import { SubjectStory } from "@/features/journal/subject-story";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { usePeopleNames } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";

export function WatchesList() {
  const t = useT();
  const me = useMe();
  const watches = useQuery(watchesQuery);
  const name = usePeopleNames();
  if (watches.isPending) return <Loading lines={2} />;
  if (watches.isError) return <Failure error={watches.error} retry={() => void watches.refetch()} />;
  const { sources } = watches.data;
  return (
    <>
      {sources.length === 0 ? (
        <Empty
          className="mb-8"
          hint={t("watch-no-source-hint", { assistant: me.assistant })}
          action={
            <Link to="/connections/catalogue" className="text-[0.85rem] text-ember hover:underline">
              {t("watch-connect-mailbox")}
            </Link>
          }
        >
          {t("watch-no-source")}
        </Empty>
      ) : null}
      <Section title={t("watch-active")} count={watches.data.watches.length}>
        {watches.data.watches.length === 0 ? (
          <Empty hint={t("watch-active-empty-hint")}>{t("watch-active-empty")}</Empty>
        ) : (
          <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
            {watches.data.watches.map((w) => (
              <li key={w.id}>
                <Link
                  to="/watches/$watchId"
                  params={{ watchId: w.id }}
                  className="group grid gap-x-6 gap-y-1 px-5 py-3.5 hover:bg-paper-sunken/60 sm:grid-cols-[minmax(0,1fr)_auto_1rem] sm:items-center"
                >
                  <span className="min-w-0">
                    <span className="block text-ink">{w.what}</span>
                    <span className="mt-0.5 flex flex-wrap gap-x-3 text-[0.85rem] text-ink-muted">
                      <span>{t("watch-for", { name: name(w.owner) })}</span>
                      <span>{w.kinds.join(", ")}</span>
                      <span>{w.once ? t("watch-once") : t("watch-every-time")}</span>
                    </span>
                  </span>
                  <span className="text-[0.85rem] text-ink-muted">
                    {w.last_triggered_at ? (
                      <>
                        {t("watch-triggered-count", { count: w.triggered })} · <Ago iso={w.last_triggered_at} />
                      </>
                    ) : (
                      t("watch-never-triggered")
                    )}
                  </span>
                  <ArrowRight
                    className="hidden size-3.5 text-ink-faint group-hover:text-ink sm:block"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  );
}

export function WatchDetail({ id }: { id: string }) {
  const t = useT();
  const found = useQuery(watchQuery(id));
  const trail: Crumb[] = [{ label: t("watch-title"), link: { to: "/watches" } }, { label: id }];
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
  const name = usePeopleNames();
  const canCancel = useCan("watches:write");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelWatch(w.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.watches });
      notify(t("watch-cancelled-notice"));
      void navigate({ to: "/watches" });
    },
  });
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={w.what}
        meta={
          <p className="flex flex-wrap gap-x-3 text-[0.85rem] text-ink-muted">
            <span>{t("watch-for", { name: name(w.owner) })}</span>
            <span>{t("watch-created", { when: moment(w.created_at) })}</span>
            {w.until ? <span>{t("watch-until", { when: moment(w.until) })}</span> : null}
          </p>
        }
        actions={
          canCancel ? (
            <Confirm
              trigger={<Button variant="destructive">{t("watch-cancel-action")}</Button>}
              title={t("watch-cancel-title")}
              confirm={t("watch-cancel")}
              onConfirm={() => cancel.mutateAsync()}
            >
              {t("watch-cancel-description", { what: w.what })}
            </Confirm>
          ) : null
        }
      />
      <div className="grid grid-cols-1 gap-10 lg:grid-cols-[minmax(0,1fr)_18rem] [&>*]:min-w-0">
        <Section title={t("watch-found")} count={w.triggered}>
          <SubjectStory filters={{ watch: w.id }} empty={t("watch-found-empty")} />
        </Section>
        <aside className="grid content-start gap-6 text-sm">
          <div>
            <p className="label-mono mb-1.5">{t("watch-watches")}</p>
            <p className="flex flex-wrap gap-1">
              {w.kinds.map((k) => (
                <Tag key={k}>{k}</Tag>
              ))}
            </p>
          </div>
          {w.keywords.length ? (
            <div>
              <p className="label-mono mb-1.5">{t("watch-keywords")}</p>
              <p className="flex flex-wrap gap-1">
                {w.keywords.map((k) => (
                  <Tag key={k}>{k}</Tag>
                ))}
              </p>
            </div>
          ) : null}
          <div>
            <p className="label-mono mb-1.5">{t("watch-rhythm")}</p>
            <p>{w.once ? t("watch-rhythm-once") : t("watch-rhythm-every")}</p>
          </div>
          {w.origin?.session ? (
            <div>
              <p className="label-mono mb-1.5">{t("watch-asked-in")}</p>
              <Link
                to="/journal"
                search={{ session: w.origin.session }}
                className="inline-flex items-center gap-2 text-ink hover:text-ember"
              >
                <MessageSquareText className="size-4" aria-hidden="true" />
                {t("watch-a-conversation")}
                {w.origin.channel ? (
                  <span className="inline-flex items-center gap-1 text-[0.85rem] text-ink-muted">
                    <KindMark kind={w.origin.channel} className="size-3" label={false} />
                    {w.origin.channel}
                  </span>
                ) : null}
              </Link>
            </div>
          ) : null}
        </aside>
      </div>
    </>
  );
}
