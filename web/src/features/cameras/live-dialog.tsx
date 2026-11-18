import { Mic, MicOff, PhoneOff, RotateCw } from "lucide-react";
import { type ReactElement, useEffect, useRef, useState } from "react";
import { ApiError, type MediaDevice, type MediaPurpose, messageOf } from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { FormActions } from "@/components/form-actions";
import { FormDialog } from "@/components/overlay-form";
import { Notice } from "@/components/states";
import { Status } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { MicrophoneError } from "@/lib/audio/microphone";
import { remaining } from "@/lib/dates";
import { deviceName } from "@/lib/labels";
import { connect, type Live, Unsupported } from "./peer";

type State =
  | { status: "connecting" }
  | { status: "live"; live: Live; until: number }
  | { status: "ended" }
  | { status: "failed"; error: unknown };

/** What went wrong, in words: the API's refusal, the microphone, or the browser. */
function problem(error: unknown): string {
  if (error instanceof ApiError) return messageOf(error);
  if (error instanceof MicrophoneError) return tr(`recording-microphone-${error.problem}`);
  if (error instanceof Unsupported) return tr("cam-unsupported");
  return tr("cam-failed");
}

/**
 * Watching a device, or calling through it, in a dialog: the session lives while the dialog is open, and ends when
 * it closes, when the page goes away, or at its longest duration.
 */
export function LiveDialog({
  device,
  purpose,
  trigger,
}: {
  device: MediaDevice;
  purpose: MediaPurpose;
  trigger: ReactElement;
}) {
  const t = useT();
  const name = deviceName(device);
  return (
    <FormDialog
      trigger={trigger}
      title={purpose === "call" ? t("cam-call-title", { name }) : t("cam-view-title", { name })}
      description={t(purpose === "call" ? "cam-call-note" : "cam-view-note", { room: device.room })}
      wide
    >
      {(close) => <Session device={device} purpose={purpose} close={close} />}
    </FormDialog>
  );
}

function Session({ device, purpose, close }: { device: MediaDevice; purpose: MediaPurpose; close: () => void }) {
  const t = useT();
  const [state, setState] = useState<State>({ status: "connecting" });
  const [attempt, setAttempt] = useState(0);
  const [muted, setMuted] = useState(false);
  const now = useNow();
  const video = useRef<HTMLVideoElement>(null);
  const live = state.status === "live" ? state.live : null;

  // biome-ignore lint/correctness/useExhaustiveDependencies: `attempt` starts it again
  useEffect(() => {
    let current: Live | null = null;
    let gone = false;
    const leave = () => current?.close(true);
    setState({ status: "connecting" });
    setMuted(false);
    // started on the next tick: a mount undone at once (React's strict mode) opens nothing on the device
    const start = setTimeout(() => {
      connect(device.id, purpose, {
        video: purpose === "view" || device.can_view,
        onEnd: () => setState({ status: "ended" }),
      }).then(
        (opened) => {
          if (gone) return opened.close();
          current = opened;
          setState({ status: "live", live: opened, until: Date.now() + opened.session.max_s * 1000 });
        },
        (error: unknown) => {
          if (!gone) setState({ status: "failed", error });
        },
      );
    });
    window.addEventListener("pagehide", leave);
    return () => {
      gone = true;
      clearTimeout(start);
      window.removeEventListener("pagehide", leave);
      current?.close();
    };
  }, [device.id, device.can_view, purpose, attempt]);

  useEffect(() => {
    if (video.current && live) video.current.srcObject = live.stream;
  }, [live]);

  useEffect(() => {
    if (state.status === "live" && now.getTime() >= state.until) {
      state.live.close();
      setState({ status: "ended" });
    }
  }, [now, state]);

  const shows = live?.session.video ?? false;
  return (
    <div className="grid gap-4">
      <div data-phase="night" className="sky grid aspect-video place-items-center">
        {/* the device's sound plays from here too, even when it sends no picture */}
        <video
          ref={video}
          autoPlay
          playsInline
          muted={!live?.session.audio}
          aria-label={t("cam-stream", { name: deviceName(device) })}
          className={shows ? "size-full object-contain" : "hidden"}
        >
          <track kind="captions" />
        </video>
        {shows ? null : (
          <div className="grid justify-items-center gap-3 p-6 text-center">
            <AgentFigure state={state.status === "connecting" ? "thinking" : "idle"} size="md" />
            <p className="text-[0.95rem]">
              {state.status === "connecting"
                ? t("cam-connecting")
                : state.status === "ended"
                  ? t("cam-ended")
                  : state.status === "live"
                    ? t("cam-audio-only", { room: device.room })
                    : null}
            </p>
          </div>
        )}
      </div>
      {state.status === "failed" ? <Notice>{problem(state.error)}</Notice> : null}
      <FormActions
        hint={
          state.status === "live" ? (
            <Status tone="accent">{t("cam-left", { remaining: remaining(state.until, now) })}</Status>
          ) : null
        }
      >
        {state.status === "live" && purpose === "call" ? (
          <Button
            variant="outline"
            aria-pressed={muted}
            onClick={() => {
              live?.mute(!muted);
              setMuted(!muted);
            }}
          >
            {muted ? <MicOff /> : <Mic />} {muted ? t("cam-unmute") : t("cam-mute")}
          </Button>
        ) : null}
        {state.status === "failed" || state.status === "ended" ? (
          <Button variant="outline" onClick={() => setAttempt((n) => n + 1)}>
            <RotateCw /> {t("cam-again")}
          </Button>
        ) : null}
        {purpose === "call" && state.status !== "failed" && state.status !== "ended" ? (
          <Button variant="destructive" onClick={close}>
            <PhoneOff /> {t("cam-hang-up")}
          </Button>
        ) : (
          <Button onClick={close}>{t("action-close")}</Button>
        )}
      </FormActions>
    </div>
  );
}
