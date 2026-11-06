/**
 * A person's voice on their page: whether it is recorded, what was learned since and when, and for
 * whoever may manage it (the person, or an owner for someone without an account) the recording,
 * learning over time, and forgetting.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Mic } from "lucide-react";
import { useState } from "react";
import { ApiError, api, keys, type Person, type Voice, voiceQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { useNotify } from "@/components/notices";
import { Failure, FormError } from "@/components/states";
import { Button } from "@/components/ui/button";
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
    if (voice.error instanceof ApiError && voice.error.code === "voices_off") {
      return canConfigure ? (
        <div>
          <p className="label-mono mb-1.5">{t("people-voice")}</p>
          <p className="text-ink-muted">{t("people-voice-off")}</p>
          <Link
            to="/config/$section"
            params={{ section: "voices" }}
            className="text-[0.85rem] text-ember hover:underline"
          >
            {t("people-voice-off-link")}
          </Link>
        </div>
      ) : null;
    }
    return <Failure error={voice.error} retry={() => void voice.refetch()} />;
  }
  return <VoiceState person={person} voice={voice.data} />;
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
    <div>
      <p className="label-mono mb-1.5">{t("people-voice")}</p>
      {voice.enrolled && voice.enrolled_at ? (
        <p className="text-ink">
          {t("people-voice-recorded")} <Ago iso={voice.enrolled_at} />
        </p>
      ) : (
        <p className="text-ink-muted">{t("people-voice-none")}</p>
      )}
      {voice.enrolled ? (
        <p className="mt-0.5 text-ink-muted">
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
      ) : null}

      {voice.manageable ? (
        <div className="mt-3 grid justify-items-start gap-2.5">
          <Button variant={voice.enrolled ? "outline" : "accent"} size="sm" onClick={() => setRecording(true)}>
            <Mic aria-hidden="true" />
            {voice.enrolled ? t("people-voice-redo") : t("people-voice-record", { own })}
          </Button>
          {voice.enrolled ? (
            <div className="flex items-center gap-2.5">
              <Switch
                id={switchId}
                checked={voice.learning}
                disabled={learning.isPending}
                onCheckedChange={(on) => learning.mutate(on)}
              />
              <label htmlFor={switchId} className="text-ink">
                {t("people-voice-learning")}
              </label>
            </div>
          ) : null}
          <FormError error={learning.error} />
          {voice.enrolled && voice.learned > 0 ? (
            <Confirm
              trigger={
                <Button variant="ghost" size="sm" className="-ml-2.5">
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
          {voice.enrolled ? (
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
          ) : null}
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
