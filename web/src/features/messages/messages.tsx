import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { api, type Confirmation, confirmationsQuery, keys, messageOf, messagesQuery, type PassedMessage } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { useNotify } from "@/components/notices";
import { RowList, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Tag } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { KindMark, kindName } from "@/lib/brands";
import { hourMinute } from "@/lib/dates";
import { personName } from "@/lib/people";

/** What waits on someone: sensitive actions to confirm, questions to answer, messages on their way. */
export function MessagesView() {
  const t = useT();
  const confirmations = useQuery(confirmationsQuery);
  const messages = useQuery(messagesQuery);
  return (
    <div className="grid gap-10">
      <Section title={t("confirmation-title")} count={confirmations.data?.length}>
        {confirmations.isPending ? (
          <Loading lines={1} />
        ) : confirmations.isError ? (
          <Failure error={confirmations.error} retry={() => void confirmations.refetch()} />
        ) : confirmations.data.length ? (
          <RowList>
            {confirmations.data.map((c) => (
              <ConfirmationRow key={c.id} confirmation={c} />
            ))}
          </RowList>
        ) : (
          <Empty hint={t("confirmation-empty-hint")}>{t("confirmation-empty")}</Empty>
        )}
      </Section>
      {messages.isPending ? (
        <Loading lines={2} />
      ) : messages.isError ? (
        <Failure error={messages.error} retry={() => void messages.refetch()} />
      ) : (
        <>
          <Section title={t("message-questions")} count={messages.data.questions.length}>
            <MessageRows messages={messages.data.questions} empty={t("message-questions-empty")} />
          </Section>
          <Section title={t("message-pending")} count={messages.data.pending.length}>
            <MessageRows messages={messages.data.pending} empty={t("message-pending-empty")} />
          </Section>
        </>
      )}
    </div>
  );
}

function MessageRows({ messages, empty }: { messages: PassedMessage[]; empty: string }) {
  const t = useT();
  if (!messages.length) return <Empty>{empty}</Empty>;
  return (
    <RowList>
      {messages.map((m) => (
        <li key={m.id} className="px-5 py-3.5">
          <p className="[overflow-wrap:anywhere] text-ink">{t("message-quoted", { text: m.text })}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-ink-muted">
            <span>
              {m.requested_by
                ? t("message-from-to", { from: m.requested_by.name, to: m.to.name })
                : t("message-to", { to: m.to.name })}
            </span>
            {m.channel ? (
              <Tag>
                <KindMark kind={m.channel} className="size-3" label={false} />
                {kindName(m.channel)}
              </Tag>
            ) : null}
            <Ago iso={m.at} />
          </p>
        </li>
      ))}
    </RowList>
  );
}

function ConfirmationRow({ confirmation: c }: { confirmation: Confirmation }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const answer = useMutation({
    mutationFn: (approved: boolean) => api.answerConfirmation(c.id, approved),
    onSuccess: (answered) => {
      void queryClient.invalidateQueries({ queryKey: keys.confirmations });
      notify(answered.approved ? t("confirmation-done-notice") : t("confirmation-refused-notice"));
    },
  });
  const what = Object.entries(c.arguments)
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`)
    .join(" · ");
  return (
    <li className="grid gap-x-6 gap-y-2 px-5 py-3.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div className="min-w-0">
        <p className="text-ink">
          <span className="font-mono text-[0.9rem]">{c.tool}</span>
          {what ? <span className="text-ink-muted"> · {what}</span> : null}
        </p>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-ink-muted">
          <span>{t("confirmation-for", { name: personName(c.person) })}</span>
          <span className="inline-flex items-center gap-1">
            <KindMark kind={c.origin.channel} className="size-3" label={false} />
            {t("confirmation-asked-in", { channel: kindName(c.origin.channel) })}
          </span>
          <span>{t("confirmation-expires", { at: hourMinute(c.expires_at) })}</span>
        </p>
      </div>
      {c.yours ? (
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={answer.isPending}
            onClick={() => answer.mutate(false, { onError: (error) => notify(messageOf(error)) })}
          >
            <X /> {t("confirmation-refuse")}
          </Button>
          <Confirm
            trigger={
              <Button size="sm" disabled={answer.isPending}>
                <Check /> {t("confirmation-approve")}
              </Button>
            }
            title={t("confirmation-approve-title")}
            confirm={t("confirmation-approve")}
            onConfirm={() => answer.mutateAsync(true)}
          >
            {t("confirmation-approve-description", { tool: c.tool })}
          </Confirm>
        </div>
      ) : (
        <span className="text-[0.85rem] text-ink-muted">{t("confirmation-not-yours")}</span>
      )}
    </li>
  );
}
