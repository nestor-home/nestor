/**
 * Recording a voice, guided like "Hey Siri": Nestor says what he keeps and asks for consent, tries
 * the microphone ("say hello", his mouth on the level), has five phrases read one at a time (a ring
 * fills a fifth with each phrase the server keeps; the end of a phrase is heard, never clicked), then
 * shows he recognises the voice and lets it be tried. Closing before the end abandons the recording:
 * nothing is kept.
 */
import type { NestorController } from "@nestor-home/character";
import { useQueryClient } from "@tanstack/react-query";
import { type MutableRefObject, useCallback, useEffect, useRef, useState } from "react";
import { api, type Heard, keys, type Person, type PhraseProblem, type VoiceRecording } from "@/api";
import { AgentFigure, type FigureState } from "@/components/agent-figure";
import { Choice } from "@/components/choice";
import { GuidedDialog } from "@/components/guided-dialog";
import { FormError, Notice } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n";
import { Endpointer, type Hearing, hearing, loudness, silence, type Utterance } from "@/lib/audio/endpoint";
import {
  type Microphone,
  type MicrophoneDevice,
  MicrophoneError,
  type MicrophoneProblem,
  microphones,
  openMicrophone,
} from "@/lib/audio/microphone";
import { voiceWav } from "@/lib/audio/wav";
import { useMe } from "@/lib/session";
import { VoiceRing } from "./voice-ring";

type Step = "consent" | "microphone" | "phrases" | "done";

/** How long without hearing anyone before saying why. */
const SILENCE_MS = 6_000;

export function VoiceRecordingDialog({
  open,
  onOpenChange,
  ...props
}: {
  person: Person;
  own: boolean;
  learning: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return open ? <RecordingFlow {...props} onClose={() => onOpenChange(false)} /> : null;
}

// -- the microphone, while the flow needs it ------------------------------------------------------

type MicrophoneState =
  | { status: "opening" }
  | { status: "open"; microphone: Microphone }
  | { status: "failed"; problem: MicrophoneProblem };

function useMicrophone(active: boolean, device: string | null, attempt: number) {
  const [state, setState] = useState<MicrophoneState>({ status: "opening" });
  const [devices, setDevices] = useState<MicrophoneDevice[]>([]);
  useEffect(() => {
    if (!active || attempt < 0) return;
    let cancelled = false;
    let opened: Microphone | null = null;
    setState({ status: "opening" });
    openMicrophone(device).then(
      (microphone) => {
        if (cancelled) return microphone.close();
        opened = microphone;
        setState({ status: "open", microphone });
        void microphones().then((found) => !cancelled && setDevices(found));
      },
      (error: unknown) => {
        if (!cancelled)
          setState({ status: "failed", problem: error instanceof MicrophoneError ? error.problem : "failed" });
      },
    );
    return () => {
      cancelled = true;
      opened?.close();
    };
  }, [active, device, attempt]);
  return { state, devices };
}

/**
 * Hears utterances while `enabled`, each from a fresh endpointer: `onLevel` with every chunk (the
 * mouth), `onUtterance` at the end of each phrase, `onSilence` when nobody was heard for a while.
 */
function useUtterances(
  microphone: Microphone | null,
  enabled: boolean,
  handlers: MutableRefObject<{
    onLevel: (level: number) => void;
    onUtterance: (utterance: Utterance) => void;
    onSilence?: (floor: number) => void;
  }>,
) {
  useEffect(() => {
    if (!microphone || !enabled) return;
    const endpointer = new Endpointer(microphone.rate, (u) => {
      heard = 0;
      handlers.current.onUtterance(u);
    });
    let heard = 0; // samples since the last utterance
    const stop = microphone.listen((samples) => {
      endpointer.push(samples);
      handlers.current.onLevel(endpointer.speaking ? loudness(endpointer.level) : loudness(endpointer.level) * 0.5);
      heard += samples.length;
      if (!endpointer.speaking && heard > (microphone.rate * SILENCE_MS) / 1000) {
        heard = 0;
        handlers.current.onSilence?.(endpointer.floor);
      }
    });
    return () => {
      stop();
      handlers.current.onLevel(0);
    };
  }, [microphone, enabled, handlers]);
}

/** Nestor's mouth on the voice's level: the ember cursor opens as it gets louder. */
function useMouth() {
  const mouth = useRef<SVGElement | null>(null);
  const onReady = useCallback((controller: NestorController) => {
    mouth.current = controller.element.querySelector<SVGElement>(".nestor-mouth");
  }, []);
  const setLevel = useCallback((level: number) => {
    if (mouth.current) mouth.current.style.transform = level > 0.02 ? `scaleY(${(1 + level * 1.8).toFixed(2)})` : "";
  }, []);
  return { onReady, setLevel };
}

// -- the flow ---------------------------------------------------------------------------------------

type Phase =
  | { kind: "listening"; feedback: "kept" | PhraseProblem | "again" | null }
  | { kind: "checking" }
  | { kind: "finishing" };

type Trying = { kind: "idle" } | { kind: "listening" } | { kind: "checking" } | { kind: "heard"; heard: Heard };

function RecordingFlow({
  person,
  own,
  learning: initialLearning,
  onClose,
}: {
  person: Person;
  own: boolean;
  learning: boolean;
  onClose: () => void;
}) {
  const t = useT();
  const me = useMe();
  const queryClient = useQueryClient();
  const assistant = me.assistant;
  const ownArg = own ? "yes" : "no";

  const [step, setStep] = useState<Step>("consent");
  const [learning, setLearning] = useState(initialLearning);
  const [device, setDevice] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [hello, setHello] = useState<Hearing | null>(null);
  const [recording, setRecording] = useState<VoiceRecording | null>(null);
  const [kept, setKept] = useState<Set<number>>(new Set());
  const [current, setCurrent] = useState(0);
  const [phase, setPhase] = useState<Phase>({ kind: "listening", feedback: null });
  const [trying, setTrying] = useState<Trying>({ kind: "idle" });
  const [error, setError] = useState<unknown>(null);
  const { onReady, setLevel } = useMouth();

  const { state: mic, devices } = useMicrophone(step !== "consent", device, attempt);
  const microphone = mic.status === "open" ? mic.microphone : null;

  // a recording still open when the dialog closes is abandoned: nothing of it is kept
  const pending = useRef<string | null>(null);
  pending.current = recording && step === "phrases" ? recording.id : null;
  useEffect(
    () => () => {
      if (pending.current) void api.abandonRecording(pending.current).catch(() => undefined);
    },
    [],
  );

  // 2. the microphone: hello
  const helloHandlers = useRef({
    onLevel: setLevel,
    onUtterance: (u: Utterance) => setHello(hearing(u)),
    onSilence: (floor: number) => setHello(silence(floor)),
  });
  useUtterances(microphone, step === "microphone", helloHandlers);

  async function begin() {
    setError(null);
    try {
      const started = await api.startRecording(person.id, learning);
      setRecording(started);
      setCurrent(started.next ?? 0);
      setKept(new Set());
      setPhase({ kind: "listening", feedback: null });
      setStep("phrases");
    } catch (failure) {
      setError(failure);
    }
  }

  // 3. the phrases
  async function say(u: Utterance) {
    if (!recording) return;
    setPhase({ kind: "checking" });
    setError(null);
    try {
      const verdict = await api.sayPhrase(recording.id, current, voiceWav(u.samples, u.rate));
      if (!verdict.kept) {
        setPhase({ kind: "listening", feedback: verdict.problem ?? "again" });
        return;
      }
      const now = new Set(kept).add(current);
      setKept(now);
      if (verdict.taken >= verdict.total) {
        setPhase({ kind: "finishing" });
        const voice = await api.finishRecording(recording.id);
        queryClient.setQueryData(keys.voice(person.id), voice);
        setStep("done");
        return;
      }
      const next = recording.phrases.findIndex((_, i) => !now.has(i));
      if (next >= 0) setCurrent(next);
      setPhase({ kind: "listening", feedback: "kept" });
    } catch (failure) {
      setError(failure);
      setPhase({ kind: "listening", feedback: null });
    }
  }
  const phraseHandlers = useRef({ onLevel: setLevel, onUtterance: (u: Utterance) => void say(u) });
  phraseHandlers.current.onUtterance = (u) => void say(u);
  useUtterances(microphone, step === "phrases" && phase.kind === "listening", phraseHandlers);

  // 4. the try
  async function hear(u: Utterance) {
    setTrying({ kind: "checking" });
    setError(null);
    try {
      setTrying({ kind: "heard", heard: await api.hear(voiceWav(u.samples, u.rate)) });
    } catch (failure) {
      setError(failure);
      setTrying({ kind: "idle" });
    }
  }
  const tryHandlers = useRef({ onLevel: setLevel, onUtterance: (u: Utterance) => void hear(u) });
  useUtterances(microphone, step === "done" && trying.kind === "listening", tryHandlers);

  const listening =
    (step === "microphone" && microphone) ||
    (step === "phrases" && phase.kind === "listening") ||
    (step === "done" && trying.kind === "listening");
  const figure: FigureState = listening
    ? "listening"
    : (step === "phrases" && phase.kind !== "listening") || trying.kind === "checking"
      ? "thinking"
      : mic.status === "failed"
        ? "concerned"
        : "idle";

  const nestor = (
    <AgentFigure
      state={figure}
      size="lg"
      label={t("recording-figure", { assistant })}
      live
      onReady={(controller) => {
        onReady(controller);
        if (step === "done") controller.gesture("greet");
      }}
      key={step === "done" ? "done" : "flow"}
    />
  );
  const total = recording?.phrases.length ?? 5;
  const stage =
    step === "phrases" || step === "done" ? (
      <VoiceRing taken={step === "done" ? total : kept.size} total={total} label={t("recording-ring")}>
        {nestor}
      </VoiceRing>
    ) : (
      nestor
    );

  const title =
    step === "consent"
      ? t("recording-title", { own: ownArg, name: person.name })
      : step === "microphone"
        ? t("recording-title-microphone")
        : step === "phrases"
          ? t("recording-title-phrase")
          : t("recording-title-done", { own: ownArg, name: person.name });

  const footer =
    step === "consent" ? (
      <Button variant="accent" onClick={() => setStep("microphone")}>
        {t("recording-start")}
      </Button>
    ) : step === "microphone" ? (
      <Button variant="accent" onClick={() => void begin()} disabled={hello !== "clear"}>
        {t("recording-continue")}
      </Button>
    ) : step === "done" ? (
      <Button variant="accent" onClick={onClose}>
        {t("recording-done")}
      </Button>
    ) : null;

  return (
    <GuidedDialog
      open
      onOpenChange={(open) => !open && onClose()}
      stage={stage}
      title={title}
      step={step}
      description={t("recording-description", { assistant })}
      footer={footer}
    >
      {step === "consent" ? (
        <Consent person={person} own={ownArg} learning={learning} onLearning={setLearning} />
      ) : null}

      {step === "microphone" ? (
        <div className="grid gap-4">
          {mic.status === "failed" ? (
            <Notice>
              <p>{t(`recording-microphone-${mic.problem}`)}</p>
              {mic.problem === "denied" || mic.problem === "missing" || mic.problem === "failed" ? (
                <Button variant="outline" size="sm" className="mt-3" onClick={() => setAttempt((n) => n + 1)}>
                  {t("recording-retry")}
                </Button>
              ) : null}
            </Notice>
          ) : (
            <p role="status" className="text-center text-ink">
              {mic.status === "opening"
                ? t("recording-microphone-opening")
                : hello
                  ? t(`recording-microphone-${hello}`)
                  : t("recording-microphone-say", { assistant })}
            </p>
          )}
          {devices.length > 1 ? (
            <div className="grid gap-1.5">
              <label htmlFor="voice-microphone" className="text-[0.8rem] font-medium text-ink">
                {t("recording-microphone")}
              </label>
              <Choice
                id="voice-microphone"
                value={device ?? devices.find((d) => d.id === microphone?.device)?.id ?? devices[0]?.id ?? ""}
                options={devices.map((d, i) => ({
                  value: d.id,
                  label: d.label || t("recording-microphone-unnamed", { n: i + 1 }),
                }))}
                onChange={(next) => {
                  setHello(null);
                  setDevice(next);
                }}
              />
            </div>
          ) : null}
          <FormError error={error} />
        </div>
      ) : null}

      {step === "phrases" && recording ? (
        <div className="grid gap-4 text-center">
          <p className="label-mono">{t("recording-phrase-count", { n: kept.size + 1, total })}</p>
          <p className="font-serif text-[1.45rem] leading-snug text-balance [overflow-wrap:anywhere] text-ink">
            {t("recording-phrase", { phrase: recording.phrases[current] ?? "" })}
          </p>
          <p role="status" className="text-ink-muted">
            {phase.kind === "checking"
              ? t("recording-checking")
              : phase.kind === "finishing"
                ? t("recording-finishing")
                : phase.feedback === "kept"
                  ? t("recording-kept")
                  : phase.feedback
                    ? t("recording-again", { problem: phase.feedback })
                    : t("recording-listening")}
          </p>
          <FormError error={error} />
        </div>
      ) : null}

      {step === "done" ? (
        <div className="grid gap-4">
          <div className="grid justify-items-center gap-2 text-center">
            {trying.kind === "heard" ? (
              <HeardResult heard={trying.heard} />
            ) : (
              <p role="status" className="text-ink-muted">
                {trying.kind === "listening"
                  ? t("recording-try-listening")
                  : trying.kind === "checking"
                    ? t("recording-checking")
                    : t("recording-try-hint")}
              </p>
            )}
            {microphone && trying.kind !== "listening" && trying.kind !== "checking" ? (
              <Button variant="outline" size="sm" onClick={() => setTrying({ kind: "listening" })}>
                {t("recording-try")}
              </Button>
            ) : null}
          </div>
          <FormError error={error} />
          <p className="text-sm text-ink-muted">{t("recording-satellite", { assistant })}</p>
        </div>
      ) : null}
    </GuidedDialog>
  );
}

function Consent({
  person,
  own,
  learning,
  onLearning,
}: {
  person: Person;
  own: "yes" | "no";
  learning: boolean;
  onLearning: (on: boolean) => void;
}) {
  const t = useT();
  return (
    <div className="grid gap-4 text-ink">
      <p className="font-serif text-[1.15rem] leading-snug text-pretty">
        {t("recording-keeps", { own, name: person.name })}
      </p>
      <p className="text-ink-muted">{t("recording-use")}</p>
      <p className="text-ink-muted">{t("recording-not-a-password")}</p>
      {own === "no" ? <p>{t("recording-other-agrees", { name: person.name })}</p> : null}
      <div className="flex items-start gap-3 rounded-md border border-rule bg-paper-raised px-4 py-3">
        <Switch
          id="voice-learning"
          checked={learning}
          onCheckedChange={onLearning}
          aria-describedby="voice-learning-hint"
          className="mt-0.5"
        />
        <div className="min-w-0">
          <label htmlFor="voice-learning" className="text-sm font-medium text-ink">
            {t("recording-learning")}
          </label>
          <p id="voice-learning-hint" className="mt-0.5 text-sm text-ink-muted">
            {t("recording-learning-hint")}
          </p>
        </div>
      </div>
      <p className="text-sm text-ink-muted">{t("recording-erase", { own, name: person.name })}</p>
    </div>
  );
}

/** Who the try sounded like, and how alike: a bar with the threshold marked on it. */
function HeardResult({ heard }: { heard: Heard }) {
  const t = useT();
  const score = Math.max(0, Math.min(1, heard.score));
  return (
    <div className="grid w-full max-w-xs justify-items-center gap-2">
      <p role="status" className="font-serif text-xl text-ink">
        {heard.person && heard.name ? t("recording-heard", { name: heard.name }) : t("recording-heard-nobody")}
      </p>
      <div aria-hidden="true" className="relative h-1.5 w-full rounded-full bg-rule">
        <div
          className={heard.person ? "h-full rounded-full bg-ember" : "h-full rounded-full bg-ink-faint"}
          style={{ width: `${score * 100}%` }}
        />
        <div className="absolute -top-1 h-3.5 w-px bg-ink" style={{ left: `${heard.threshold * 100}%` }} />
      </div>
      <p className="text-sm text-ink-muted tabular">
        {t("recording-likeness", {
          score: Math.round(heard.score * 100),
          threshold: Math.round(heard.threshold * 100),
        })}
      </p>
    </div>
  );
}
