import { useQuery } from "@tanstack/react-query";
import { Link, type LinkProps } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { type JournalEvent, journalEventQuery } from "@/api";
import { CopyButton } from "@/components/copy-field";
import { Failure, Loading } from "@/components/states";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { KindMark } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { kindStyle } from "@/lib/icons";
import { say, why } from "@/lib/messages";
import { usePeopleNames } from "@/lib/people";
import { duration } from "@/lib/time";
import { cn } from "@/lib/utils";

/** One event in full: what it says, what it relates to, and the raw record for debugging. */
export function EventSheet({ id, onClose }: { id: string | undefined; onClose: () => void }) {
  const mobile = useIsMobile();
  return (
    <Sheet open={Boolean(id)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side={mobile ? "bottom" : "right"}
        className={
          mobile
            ? "h-[100dvh] w-full overflow-y-auto overscroll-contain bg-paper pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]"
            : "w-full overflow-y-auto overscroll-contain bg-paper sm:max-w-xl"
        }
      >
        {id ? <EventDetail id={id} /> : null}
      </SheetContent>
    </Sheet>
  );
}

function EventDetail({ id }: { id: string }) {
  const t = useT();
  const event = useQuery(journalEventQuery(id));
  if (event.isPending) {
    return (
      <div className="p-6">
        <SheetTitle className="sr-only">{t("jr-event")}</SheetTitle>
        <Loading lines={3} />
      </div>
    );
  }
  if (event.isError) {
    return (
      <div className="p-6">
        <SheetTitle className="mb-4 font-serif text-2xl font-normal">{t("jr-event")}</SheetTitle>
        <Failure error={event.error} />
      </div>
    );
  }
  return <Loaded event={event.data} />;
}

interface Related {
  label: string;
  person?: boolean;
  value: string;
  link: LinkProps;
}

function useRelated(event: JournalEvent): Related[] {
  const name = usePeopleNames();
  const { links } = event;
  const related: Related[] = [];
  for (const person of event.people)
    related.push({
      label: tr("jr-related-person"),
      person: true,
      value: name(person),
      link: { to: "/people/$personId", params: { personId: person } },
    });
  if (links.conversation)
    related.push({
      label: tr("jr-related-conversation"),
      value: links.conversation,
      link: { to: "/journal", search: { conversation: links.conversation } },
    });
  if (links.session)
    related.push({
      label: tr("jr-related-session"),
      value: links.session,
      link: { to: "/journal", search: { session: links.session } },
    });
  if (links.task)
    related.push({
      label: tr("jr-related-task"),
      value: links.task,
      link: { to: "/tasks/$taskId", params: { taskId: links.task } },
    });
  if (links.watch)
    related.push({
      label: tr("jr-related-watch"),
      value: links.watch,
      link: { to: "/watches/$watchId", params: { watchId: links.watch } },
    });
  if (links.connection)
    related.push({
      label: tr("jr-related-connection"),
      value: links.connection,
      link: { to: "/connections/$connectionId", params: { connectionId: links.connection } },
    });
  if (links.satellite)
    related.push({
      label: tr("jr-related-satellite"),
      value: links.satellite,
      link: { to: "/satellites/$satelliteId", params: { satelliteId: links.satellite } },
    });
  if (links.memory)
    related.push({ label: tr("jr-related-memory"), value: links.memory, link: { to: "/memories", search: {} } });
  if (event.cause)
    related.push({
      label: tr("jr-related-cause"),
      value: event.cause,
      link: { to: "/journal", search: { event: event.cause } },
    });
  return related;
}

function Loaded({ event }: { event: JournalEvent }) {
  const t = useT();
  const style = kindStyle(event.kind);
  const Icon = style.icon;
  const related = useRelated(event);
  const raw = JSON.stringify(event.record, null, 2);
  return (
    <>
      <SheetHeader className="border-b border-rule px-6 pt-6 pb-4">
        <p className="flex items-center gap-2 font-mono text-xs text-ink-muted">
          <Icon className={cn("size-3.5", style.tone)} aria-hidden="true" />
          <span>{event.type}</span>
          {event.brand ? <KindMark kind={event.brand} className="size-3.5" /> : null}
        </p>
        <SheetTitle className="mt-1 font-serif text-2xl leading-tight font-normal">{say(event)}</SheetTitle>
        <SheetDescription className="font-mono text-xs tabular">
          {moment(event.at)}
          {event.room ? ` · ${t("jr-event-room", { room: event.room })}` : ""}
          {event.outcome?.duration_s ? ` · ${duration(event.outcome.duration_s)}` : ""}
        </SheetDescription>
      </SheetHeader>
      <div className="grid min-w-0 grid-cols-1 gap-6 px-6 pb-8">
        {event.reason ? (
          <p className="rounded-sm bg-ember-soft/70 px-3 py-2 text-sm">
            <span className="font-mono text-[0.72rem] text-ember">{t("jr-why")} </span>
            {why(event)}
          </p>
        ) : null}
        {event.detail ? <p className="text-[0.95rem] leading-relaxed whitespace-pre-line">{event.detail}</p> : null}

        {related.length ? (
          <section aria-labelledby="related">
            <h3 id="related" className="mb-2 border-b border-rule pb-1.5 font-serif text-lg font-normal">
              {t("jr-related")}
            </h3>
            <dl className="grid grid-cols-[7rem_1fr] gap-x-4 gap-y-1.5 text-sm">
              {related.map((r) => (
                <div key={`${r.label}-${r.value}`} className="contents">
                  <dt className="label-mono pt-0.5">{r.label}</dt>
                  <dd>
                    <Link {...r.link} className="inline-flex items-center gap-1 text-ink hover:text-ember">
                      <span className={r.person ? "" : "font-mono text-[0.8rem]"}>{r.value}</span>
                      <ArrowUpRight className="size-3" aria-hidden="true" />
                    </Link>
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}

        <section aria-labelledby="raw">
          <div className="mb-2 flex items-center justify-between border-b border-rule pb-1.5">
            <h3 id="raw" className="font-serif text-lg font-normal">
              {t("jr-raw")}
            </h3>
            <span className="flex items-center gap-3 font-mono text-[0.7rem] text-ink-faint">
              {event.id}
              <CopyButton value={raw} label={t("jr-raw-copy")} />
            </span>
          </div>
          <pre className="max-h-80 overflow-auto rounded-sm bg-paper-sunken p-3 font-mono text-[0.72rem] leading-relaxed text-ink">
            {raw}
          </pre>
        </section>
      </div>
    </>
  );
}
