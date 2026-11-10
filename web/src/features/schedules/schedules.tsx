import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { api, keys, type Schedule, schedulesQuery } from "@/api";
import { Confirm } from "@/components/confirm";
import { useNotify } from "@/components/notices";
import { OriginLink } from "@/components/origin-link";
import { RowList, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Tag } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { moment } from "@/lib/dates";
import { weekdayLabel } from "@/lib/labels";
import { personName } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";

/** Wake-ups and reminders: what the agent will do later on its own, soonest first, and cancelling one. */
export function SchedulesList() {
  const t = useT();
  const me = useMe();
  const schedules = useQuery(schedulesQuery);
  if (schedules.isPending) return <Loading lines={3} />;
  if (schedules.isError) return <Failure error={schedules.error} retry={() => void schedules.refetch()} />;
  const { schedules: all } = schedules.data;
  const once = all.filter((s) => !s.recurring);
  const recurring = all.filter((s) => s.recurring);
  if (!all.length)
    return <Empty hint={t("schedule-empty-hint", { assistant: me.assistant })}>{t("schedule-empty")}</Empty>;
  return (
    <div className="grid gap-10">
      {once.length ? (
        <Section title={t("schedule-once")} count={once.length}>
          <ScheduleRows schedules={once} />
        </Section>
      ) : null}
      {recurring.length ? (
        <Section title={t("schedule-recurring")} count={recurring.length}>
          <ScheduleRows schedules={recurring} />
        </Section>
      ) : null}
    </div>
  );
}

function ScheduleRows({ schedules }: { schedules: Schedule[] }) {
  return (
    <RowList>
      {schedules.map((s) => (
        <ScheduleRow key={s.id} schedule={s} />
      ))}
    </RowList>
  );
}

/** When a recurring one runs, in words: `Saturday, Sunday · 08:00`, `every day · 08:00, 18:00`. */
function rhythm(s: Schedule): string {
  const times = s.times.join(", ");
  const days = s.days.length ? s.days.map(weekdayLabel).join(", ") : tr("schedule-every-day");
  return `${days} · ${times}`;
}

function ScheduleRow({ schedule: s }: { schedule: Schedule }) {
  const t = useT();
  const canCancel = useCan("schedules:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: () => api.cancelSchedule(s.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.schedules });
      notify(t("schedule-cancelled-notice"));
    },
  });
  return (
    <li className="grid gap-x-6 gap-y-1.5 px-5 py-3.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div className="min-w-0">
        <p className="[overflow-wrap:anywhere] text-ink">{s.instruction}</p>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-ink-muted">
          <span>{t("schedule-for", { name: personName(s.owner) })}</span>
          {s.recurring ? <Tag>{rhythm(s)}</Tag> : null}
          {s.next_due ? <span>{t("schedule-next", { when: moment(s.next_due) })}</span> : null}
          {s.origin ? <OriginLink origin={s.origin} /> : null}
        </p>
      </div>
      {canCancel ? (
        <Confirm
          trigger={
            <Button variant="ghost" size="sm" aria-label={t("schedule-cancel-for", { what: s.instruction })}>
              <Trash2 /> {t("schedule-cancel")}
            </Button>
          }
          title={t("schedule-cancel-title")}
          confirm={t("schedule-cancel-confirm")}
          onConfirm={() => cancel.mutateAsync()}
        >
          {t("schedule-cancel-description", { what: s.instruction })}
        </Confirm>
      ) : null}
    </li>
  );
}
