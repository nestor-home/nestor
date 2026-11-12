/**
 * A voice message recorded in the page, as messaging apps do: the browser's own encoder (Opus in WebM or Ogg, AAC
 * in MP4 on Safari), how long it has lasted, and how loud it is now, for the composer to show it is listening.
 */
import { useCallback, useEffect, useRef, useState } from "react";

const TYPES = ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/mp4"];

export type RecorderState =
  | { state: "idle" }
  | { state: "recording"; seconds: number; level: number }
  | { state: "refused" }; // no microphone, or the browser refused it

interface Session {
  recorder: MediaRecorder;
  stream: MediaStream;
  context: AudioContext;
  frame: number;
  started: number;
  chunks: Blob[];
}

export function useRecorder() {
  const [status, setStatus] = useState<RecorderState>({ state: "idle" });
  const session = useRef<Session | null>(null);
  const asking = useRef(false); // the browser is asking for the microphone
  const mounted = useRef(true);

  const release = useCallback(() => {
    const current = session.current;
    session.current = null;
    if (!current) return;
    cancelAnimationFrame(current.frame);
    for (const track of current.stream.getTracks()) track.stop();
    void current.context.close();
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      release();
    };
  }, [release]);

  const start = useCallback(async () => {
    if (session.current || asking.current) return;
    asking.current = true;
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      setStatus({ state: "refused" });
      return;
    } finally {
      asking.current = false;
    }
    if (!mounted.current) {
      for (const track of stream.getTracks()) track.stop(); // left during the browser's question
      return;
    }
    const mimeType = TYPES.find((type) => MediaRecorder.isTypeSupported(type));
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const current: Session = { recorder, stream, context, frame: 0, started: performance.now(), chunks: [] };
    recorder.ondataavailable = (event) => current.chunks.push(event.data);
    let shown = 0;
    const tick = (now: number) => {
      if (now - shown >= 80) {
        // about 12 times a second: enough for the eye, light on the page
        shown = now;
        analyser.getFloatTimeDomainData(samples);
        const rms = Math.sqrt(samples.reduce((sum, s) => sum + s * s, 0) / samples.length);
        setStatus({ state: "recording", seconds: (now - current.started) / 1000, level: Math.min(1, rms * 6) });
      }
      current.frame = requestAnimationFrame(tick);
    };
    session.current = current;
    recorder.start(250);
    tick(performance.now());
  }, []);

  /** The recording, once stopped; `null` when nothing was recorded. */
  const finish = useCallback(async (): Promise<Blob | null> => {
    const current = session.current;
    if (!current) return null;
    const stopped = new Promise<void>((resolve) => {
      current.recorder.onstop = () => resolve();
    });
    current.recorder.stop();
    await stopped;
    release();
    setStatus({ state: "idle" });
    const blob = new Blob(current.chunks, { type: current.recorder.mimeType || "audio/webm" });
    return blob.size ? blob : null;
  }, [release]);

  const cancel = useCallback(() => {
    session.current?.recorder.stop();
    release();
    setStatus({ state: "idle" });
  }, [release]);

  return { status, start, finish, cancel };
}
