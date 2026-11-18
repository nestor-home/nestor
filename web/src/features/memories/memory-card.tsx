import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight, BookMarked, Pencil, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import { api, type Memory } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { FormActions } from "@/components/form-actions";
import { Avatar } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { FormDialog, SheetPanel } from "@/components/overlay-form";
import { Fact, Facts } from "@/components/page";
import { FormError } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import { KindMark, kindName } from "@/lib/brands";
import { moment } from "@/lib/dates";

/** One thing the agent knows, in its own words; `about` names whom it concerns when the list does not. */
export function MemoryCard({ memory, about, onOpen }: { memory: Memory; about: boolean; onOpen: () => void }) {
  const t = useT();
  return (
    <li>
      <button type="button" className="surface flex h-full w-full flex-col gap-3 p-4 text-left" onClick={onOpen}>
        <span className="min-w-0 flex-1 title-sub text-ink [font-variation-settings:'opsz'_18]">{memory.text}</span>
        <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-meta text-ink-muted">
          {about ? (
            <span className="inline-flex items-center gap-1.5 text-ink">
              {memory.about ? <Avatar name={memory.about.name} size="xs" /> : null}
              {memory.about?.name ?? t("household-everyone")}
            </span>
          ) : null}
          {memory.told_by ? <span>{t("mem-told-by", { name: memory.told_by.name })}</span> : null}
          <Ago iso={memory.updated_at} />
        </span>
      </button>
    </li>
  );
}

/** A memory, opened: whom it is about, who said it and where, then correcting or forgetting it. */
export function MemoryPanel({ memory, editable, onDone }: { memory: Memory; editable: boolean; onDone: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const forget = useMutation({
    mutationFn: () => api.forgetMemory(memory.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["memories"] });
      notify(t("mem-forgotten"));
      onDone();
    },
  });
  return (
    <SheetPanel
      icon={BookMarked}
      tone="sage"
      kind={t("mem-kind")}
      title={memory.text}
      actions={
        memory.learnt_event || editable ? (
          <>
            {memory.learnt_event ? (
              <Link
                to="/journal"
                search={{ event: memory.learnt_event, ...(memory.session ? { session: memory.session } : {}) }}
                className={buttonVariants({ variant: "outline" })}
              >
                {t("mem-learnt-where")} <ArrowUpRight />
              </Link>
            ) : null}
            {editable ? (
              <>
                <FormDialog
                  trigger={
                    <Button variant="outline">
                      <Pencil /> {t("mem-correct")}
                    </Button>
                  }
                  title={t("mem-correct-title")}
                  description={t("mem-correct-description")}
                >
                  {(close) => <CorrectForm memory={memory} onDone={close} />}
                </FormDialog>
                <Confirm
                  trigger={
                    <Button variant="destructive">
                      <Trash2 /> {t("mem-forget")}
                    </Button>
                  }
                  title={t("mem-forget-title")}
                  confirm={t("mem-forget-confirm")}
                  onConfirm={() => forget.mutateAsync()}
                >
                  {t("mem-forget-text", { text: memory.text })}
                </Confirm>
              </>
            ) : null}
          </>
        ) : undefined
      }
    >
      <Facts narrow className="text-body">
        <Fact term={t("mem-about-label")}>
          {memory.about ? (
            <Link
              to="/people/$personId"
              params={{ personId: memory.about.id }}
              className="inline-flex items-center gap-2 text-ink hover:text-ember"
            >
              <Avatar name={memory.about.name} size="sm" />
              {memory.about.name}
            </Link>
          ) : (
            t("household-everyone")
          )}
        </Fact>
        {memory.told_by ? <Fact term={t("mem-told-by-label")}>{memory.told_by.name}</Fact> : null}
        {memory.learnt_in ? (
          <Fact term={t("mem-learnt-in")} className="flex items-center gap-1.5">
            <KindMark kind={memory.learnt_in} className="size-3.5" label={false} />
            {kindName(memory.learnt_in)}
          </Fact>
        ) : null}
        <Fact term={t("mem-kept-since")}>{moment(memory.created_at)}</Fact>
        {memory.updated_at === memory.created_at ? null : (
          <Fact term={t("mem-changed")}>
            <Ago iso={memory.updated_at} />
          </Fact>
        )}
      </Facts>
    </SheetPanel>
  );
}

function CorrectForm({ memory, onDone }: { memory: Memory; onDone: () => void }) {
  const t = useT();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const [text, setText] = useState(memory.text);
  const correct = useMutation({
    mutationFn: () => api.correctMemory(memory.id, text.trim()),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["memories"] });
      notify(t("mem-corrected"));
      onDone();
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    correct.mutate();
  }
  const id = `memory-${memory.id}`;
  return (
    <form onSubmit={submit} className="grid gap-3">
      <Label htmlFor={id}>{t("mem-text")}</Label>
      <Textarea
        id={id}
        rows={3}
        required
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
        }}
      />
      <FormError error={correct.error} />
      <FormActions hint={t("mem-save-hint")}>
        <Button type="submit" disabled={correct.isPending || !text.trim() || text.trim() === memory.text}>
          {correct.isPending ? t("action-saving") : t("action-save")}
        </Button>
      </FormActions>
    </form>
  );
}
