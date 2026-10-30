import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { type FormEvent, useState } from "react";
import { api, type Memory } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { useNotify } from "@/components/notices";
import { FormDialog } from "@/components/overlay-form";
import { FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { usePeopleNames } from "@/lib/people";

export function MemoryCard({ memory, editable }: { memory: Memory; editable: boolean }) {
  const t = useT();
  const name = usePeopleNames();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const forget = useMutation({
    mutationFn: () => api.forgetMemory(memory.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["memories"] });
      notify(t("mem-forgotten"));
    },
  });
  return (
    <li className="group grid gap-3 rounded-md border border-rule bg-paper-raised px-5 py-4">
      <p className="font-serif text-[1.1rem] leading-snug text-ink [font-variation-settings:'opsz'_18]">
        {memory.text}
      </p>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[0.85rem] text-ink-muted">
          <span>
            {t("mem-about-label")}{" "}
            {memory.about ? (
              <Link to="/people/$personId" params={{ personId: memory.about }} className="text-ember hover:underline">
                {name(memory.about)}
              </Link>
            ) : (
              <span className="text-ember">{t("household-everyone")}</span>
            )}
          </span>
          {memory.told_by ? <span>{t("mem-told-by", { name: name(memory.told_by) })}</span> : null}
          {memory.channel ? (
            <span className="inline-flex items-center gap-1">
              <KindMark kind={memory.channel} className="size-3" label={false} />
              {memory.channel}
            </span>
          ) : null}
          <Ago iso={memory.updated_at} />
          {memory.learnt_event ? (
            <Link
              to="/journal"
              search={{ event: memory.learnt_event, ...(memory.session ? { session: memory.session } : {}) }}
              className="inline-flex items-center gap-0.5 text-ink hover:text-ember"
            >
              {t("mem-learnt-where")} <ArrowUpRight className="size-3" aria-hidden="true" />
            </Link>
          ) : null}
        </p>
        {editable ? (
          <span className="flex gap-1.5">
            <FormDialog
              trigger={
                <Button variant="ghost" size="sm">
                  {t("mem-correct")}
                </Button>
              }
              title={t("mem-correct-title")}
              description={t("mem-correct-description")}
            >
              {(close) => <CorrectForm memory={memory} onDone={close} />}
            </FormDialog>
            <Confirm
              trigger={
                <Button variant="ghost" size="sm" className="text-brick hover:text-brick">
                  {t("mem-forget")}
                </Button>
              }
              title={t("mem-forget-title")}
              confirm={t("mem-forget-confirm")}
              onConfirm={() => forget.mutateAsync()}
            >
              {t("mem-forget-text", { text: memory.text })}
            </Confirm>
          </span>
        ) : null}
      </div>
    </li>
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
      <div className="flex items-center justify-end gap-3">
        <span className="font-mono text-[0.7rem] text-ink-faint">{t("mem-save-hint")}</span>
        <Button type="submit" disabled={correct.isPending || !text.trim() || text.trim() === memory.text}>
          {correct.isPending ? t("action-saving") : t("action-save")}
        </Button>
      </div>
    </form>
  );
}
