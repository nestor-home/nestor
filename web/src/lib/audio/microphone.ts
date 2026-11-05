/**
 * The browser's microphone, for recording a voice: asked once, then heard as raw samples through an
 * AudioWorklet (served from the admin's own origin, as its security policy requires). No echo
 * cancellation nor noise suppression: the voiceprint must match what satellites hear.
 */
import captureUrl from "./capture.worklet.ts?worker&url";

export type MicrophoneProblem = "insecure" | "unsupported" | "denied" | "missing" | "failed";

export class MicrophoneError extends Error {
  constructor(readonly problem: MicrophoneProblem) {
    super(`microphone ${problem}`);
    this.name = "MicrophoneError";
  }
}

export interface MicrophoneDevice {
  id: string;
  label: string;
}

export interface Microphone {
  rate: number;
  device: string | null; // the device id actually opened
  /** Hears the samples as they come; returns the function that stops hearing them. */
  listen(onSamples: (samples: Float32Array) => void): () => void;
  close(): void;
}

function problemOf(error: unknown): MicrophoneProblem {
  const name = error instanceof DOMException || error instanceof Error ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "denied";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "missing";
  return "failed";
}

/** Opens a microphone (the chosen one, else the browser's default), asking permission if needed. */
export async function openMicrophone(device?: string | null): Promise<Microphone> {
  if (typeof window !== "undefined" && !window.isSecureContext) throw new MicrophoneError("insecure");
  if (!navigator.mediaDevices?.getUserMedia || typeof AudioContext === "undefined") {
    throw new MicrophoneError("unsupported");
  }
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        ...(device ? { deviceId: { exact: device } } : {}),
        channelCount: 1,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: true,
      },
    });
  } catch (error) {
    throw new MicrophoneError(problemOf(error));
  }
  const context = new AudioContext();
  const stop = () => {
    for (const track of stream.getTracks()) track.stop();
    void context.close();
  };
  try {
    await context.audioWorklet.addModule(captureUrl);
    await context.resume();
  } catch {
    stop();
    throw new MicrophoneError("failed");
  }
  const source = context.createMediaStreamSource(stream);
  const capture = new AudioWorkletNode(context, "nestor-capture", { numberOfInputs: 1, numberOfOutputs: 0 });
  source.connect(capture);
  const listeners = new Set<(samples: Float32Array) => void>();
  capture.port.onmessage = (event: MessageEvent<Float32Array>) => {
    for (const listener of listeners) listener(event.data);
  };
  return {
    rate: context.sampleRate,
    device: stream.getAudioTracks()[0]?.getSettings().deviceId ?? null,
    listen(onSamples) {
      listeners.add(onSamples);
      return () => listeners.delete(onSamples);
    },
    close() {
      listeners.clear();
      capture.port.onmessage = null;
      source.disconnect();
      stop();
    },
  };
}

/** The microphones the browser shows, named once permission is given. */
export async function microphones(): Promise<MicrophoneDevice[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((d) => d.kind === "audioinput" && d.deviceId && d.deviceId !== "communications")
    .map((d) => ({ id: d.deviceId, label: d.label }));
}
