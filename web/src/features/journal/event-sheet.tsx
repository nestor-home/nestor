import { useQuery } from "@tanstack/react-query";
import { Link, type LinkProps } from "@tanstack/react-router";
import { ArrowUpRight, ScrollText } from "lucide-react";
import { type JournalEvent, type JournalItem, journalEventQuery } from "@/api";
import { CopyButton } from "@/components/copy-field";
import { Avatar } from "@/components/marks";
import { SheetPanel, SideSheet } from "@/components/overlay-form";
import { Fact, Facts } from "@/components/page";
import { Failure, Loading } from "@/components/states";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { KindName } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { kindLabel } from "@/lib/labels";
import { say, why } from "@/lib/messages";
import { duration } from "@/lib/time";
import { Attachments } from "./attachments";
import { tileOf } from "./tile";

/** One event in full: what it says and why, what it relates to, and the raw record for whoever debugs. */
export function EventSheet({ position, onClose }: { position: number | undefined; onClose: () => void }) {
  return (
    <SideSheet open={Boolean(position)} onOpenChange={(open) => !open && onClose()}>
      {position ? <EventDetail position={position} /> : null}
    </SideSheet>
  );
}

function EventDetail({ position }: { position: number }) {
  const t = useT();
  const event = useQuery(journalEventQuery(position));
  if (event.isSuccess) return <Loaded event={event.data} />;
  return (
    <SheetPanel icon={ScrollText} kind={t("jr-title")} title={t("jr-event")}>
      {event.isError ? <Failure error={event.error} retry={() => void event.refetch()} /> : <Loading lines={3} />}
    </SheetPanel>
  );
}

interface Related {
  label: string;
  person?: boolean;
  value: string;
  link: LinkProps;
}

function useRelated(item: JournalItem): Related[] {
  const { links } = item;
  const related: Related[] = [];
  for (const person of item.people)
    related.push({
      label: tr("jr-related-person"),
      person: true,
      value: person.name,
      link: { to: "/people/$personId", params: { personId: person.id } },
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
  if (links.alert)
    related.push({
      label: tr("jr-related-alert"),
      value: links.alert,
      link: { to: "/alerts/$alertId", params: { alertId: links.alert } },
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
  if (item.cause)
    related.push({
      label: tr("jr-related-cause"),
      value: String(item.cause),
      link: { to: "/journal", search: { event: item.cause } },
    });
  return related;
}

function Loaded({ event: { item: event, record } }: { event: JournalEvent }) {
  const t = useT();
  const related = useRelated(event);
  const raw = JSON.stringify(record, null, 2);
  const seconds = event.outcome?.duration_s;
  return (
    <SheetPanel {...tileOf(event)} kind={kindLabel(event.kind)} title={say(event)} description={moment(event.at)}>
      {event.reason ? (
        <p className="rounded-xl bg-ember-soft px-4 py-3 text-body text-ink">
          <span className="font-medium text-ember">{t("jr-why-label")} </span>
          {why(event)}
        </p>
      ) : null}
      {event.detail_text ? (
        event.kind === "tool" ? (
          <pre className="code-block min-w-0">{event.detail_text}</pre>
        ) : (
          <p className="min-w-0 title-sub whitespace-pre-line">{event.detail_text}</p>
        )
      ) : null}
      <Attachments item={event} />

      <Facts narrow>
        {event.room ? <Fact term={t("jr-fact-room")}>{event.room}</Fact> : null}
        {event.channels.length ? (
          <Fact term={t("jr-fact-channel")} className="flex flex-wrap items-center gap-x-3">
            {event.channels.map((c) => (
              <KindName key={c} kind={c} />
            ))}
          </Fact>
        ) : null}
        {event.brand ? (
          <Fact term={t("jr-fact-through")}>
            <KindName kind={event.brand} />
          </Fact>
        ) : null}
        {seconds !== undefined && seconds !== null ? <Fact term={t("jr-fact-took")}>{duration(seconds)}</Fact> : null}
        {related.map((r) => (
          <Fact key={`${r.label}-${r.value}`} term={r.label}>
            <Link {...r.link} className="inline-flex max-w-full items-center gap-1 text-ink hover:text-ember">
              {r.person ? <Avatar name={r.value} size="xs" /> : null}
              <span className={r.person ? "" : "truncate font-mono text-meta"}>{r.value}</span>
              <ArrowUpRight className="size-3 shrink-0" aria-hidden="true" />
            </Link>
          </Fact>
        ))}
      </Facts>

      <section aria-labelledby="raw" className="min-w-0">
        <div className="mb-2 flex items-baseline justify-between gap-3">
          <h3 id="raw" className="title-sub text-ink">
            {t("jr-raw")}
          </h3>
          <CopyButton value={raw} label={t("jr-raw-copy")} />
        </div>
        <p className="min-w-0 mb-2 font-mono text-meta text-ink-muted">
          {event.type} · {event.id}
        </p>
        <pre className="code-block max-h-80 min-w-0 overflow-y-auto">{raw}</pre>
      </section>
    </SheetPanel>
  );
}
