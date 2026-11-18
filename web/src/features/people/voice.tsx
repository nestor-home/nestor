/**
 * A person's voice on their page: whether it is recorded, what was learned since and when, and for
 * whoever may manage it (the person, or an owner for someone without an account) the recording,
 * learning over time, and forgetting. Absent when voices are off and the reader cannot turn them on.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, AudioLines, Mic } from "lucide-react";
import { useState } from "react";
import { ApiError, api, keys, type Person, type Voice, voiceQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { IconTile } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { Section } from "@/components/page";
import { Empty, Failure, FormError } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n";
import { useCan, useMe } from "@/lib/session";
import { VoiceRecordingDialog } from "./voice-recording";

export function PersonVoice({ person }: { person: Person }) {
  const t = useT();
  const voice = useQuery(voiceQuery(person.id));
  const canConfigure = useCan("config:manage");
  if (voice.isPending) return null;
  if (voice.isError) {
    const off = voice.error instanceof ApiError && voice.error.code === "voices_off";
    if (off && !canConfigure) return null;
    return (
      <Section title={t("people-voice")}>
        {off ? (
          <Empty
            action={
              <Link
                to="/config/$section"
                params={{ section: "voices" }}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                {t("people-voice-off-link")} <ArrowRight />
              </Link>
            }
          >
            {t("people-voice-off")}
          </Empty>
        ) : (
          <Failure error={voice.error} retry={() => void voice.refetch()} />
        )}
      </Section>
    );
  }
  return (
    <Section title={t("people-voice")}>
      <VoiceState person={person} voice={voice.data} />
    </Section>
  );
}

function VoiceState({ person, voice }: { person: Person; voice: Voice }) {
  const t = useT();
  const me = useMe();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const [recording, setRecording] = useState(false);
  const own = me.account.person?.id === person.id ? "yes" : "no";
  const remember = (next: Voice) => queryClient.setQueryData(keys.voice(person.id), next);
  const learning = useMutation({
    mutationFn: (on: boolean) => api.setVoiceLearning(person.id, on),
    onSuccess: (next) => {
      remember(next);
      notify(t(next.learning ? "people-voice-learning-on" : "people-voice-learning-off", { assistant: me.assistant }));
    },
  });
  const switchId = `voice-learning-${person.id}`;

  return (
    <div className="surface">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 p-5">
        <IconTile icon={AudioLines} tone={voice.enrolled ? "sage" : "ink"} size="lg" />
        <div className="min-w-0 flex-1 basis-56">
          {voice.enrolled && voice.enrolled_at ? (
            <p className="font-medium text-ink">
              {t("people-voice-recorded")} <Ago iso={voice.enrolled_at} />
            </p>
          ) : (
            <p className="font-medium text-ink">{t("people-voice-none")}</p>
          )}
          {voice.enrolled ? (
            <p className="mt-0.5 text-body text-ink-muted">
              {voice.learning || voice.learned ? (
                <>
                  {t("people-voice-learned", { count: voice.learned })}
                  {voice.learned && voice.last_learned_at ? (
                    <>
                      {" "}
                      <Ago iso={voice.last_learned_at} />.
                    </>
                  ) : null}
                </>
              ) : null}
              {voice.learning ? null : <span className="block">{t("people-voice-not-learning")}</span>}
            </p>
          ) : (
            <p className="mt-0.5 text-body text-ink-muted">{t("people-voice-why", { assistant: me.assistant })}</p>
          )}
        </div>
        {voice.manageable ? (
          <Button variant={voice.enrolled ? "outline" : "accent"} onClick={() => setRecording(true)}>
            <Mic aria-hidden="true" />
            {voice.enrolled ? t("people-voice-redo") : t("people-voice-record", { own })}
          </Button>
        ) : null}
      </div>
      {voice.manageable && voice.enrolled ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-rule px-5 py-3.5">
          <div className="mr-auto flex items-center gap-2.5">
            <Switch
              id={switchId}
              checked={voice.learning}
              disabled={learning.isPending}
              onCheckedChange={(on) => learning.mutate(on)}
            />
            <label htmlFor={switchId} className="text-body text-ink">
              {t("people-voice-learning")}
            </label>
          </div>
          <FormError error={learning.error} />
          {voice.learned > 0 ? (
            <Confirm
              trigger={
                <Button variant="ghost" size="sm">
                  {t("people-voice-forget-learned")}
                </Button>
              }
              title={t("people-voice-forget-learned-title")}
              confirm={t("people-voice-forget-confirm")}
              onConfirm={async () => {
                remember(await api.forgetVoice(person.id, true));
                notify(t("people-voice-learned-forgotten"));
              }}
            >
              {t("people-voice-forget-learned-body", { count: voice.learned })}
            </Confirm>
          ) : null}
          <Confirm
            trigger={
              <Button variant="destructive" size="sm">
                {t("people-voice-forget", { own })}
              </Button>
            }
            title={t("people-voice-forget-title", { own, name: person.name })}
            confirm={t("people-voice-forget-confirm")}
            onConfirm={async () => {
              remember(await api.forgetVoice(person.id));
              notify(t("people-voice-forgotten"));
            }}
          >
            {t("people-voice-forget-body", { assistant: me.assistant, name: person.name })}
          </Confirm>
        </div>
      ) : null}
      <VoiceRecordingDialog
        person={person}
        own={own === "yes"}
        learning={voice.enrolled ? voice.learning : true}
        open={recording}
        onOpenChange={setRecording}
      />
    </div>
  );
}
