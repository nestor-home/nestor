/**
 * The browser's microphone in tests, driven by hand: what it hears is what `speak` says. A test file
 * replaces the real module with `vi.mock("@/lib/audio/microphone", () => import("@/test/microphone").then((m) => m.module()))`.
 */
import { act, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import type * as Real from "@/lib/audio/microphone";

export const microphone = {
  listeners: new Set<(samples: Float32Array) => void>(),
  open: 0,
  problem: null as null | Real.MicrophoneProblem,
  reset() {
    this.listeners.clear();
    this.open = 0;
    this.problem = null;
  },
};

export async function module(): Promise<typeof Real> {
  const real = await vi.importActual<typeof Real>("@/lib/audio/microphone");
  return {
    ...real,
    openMicrophone: async () => {
      if (microphone.problem) throw new real.MicrophoneError(microphone.problem);
      microphone.open++;
      return {
        rate: RATE,
        device: "desk",
        listen(onSamples) {
          microphone.listeners.add(onSamples);
          return () => microphone.listeners.delete(onSamples);
        },
        close() {
          microphone.open--;
          microphone.listeners.clear();
        },
      };
    },
    microphones: async () => [
      { id: "desk", label: "Desk microphone" },
      { id: "headset", label: "Headset" },
    ],
  };
}

const RATE = 16_000;
const sound = (seconds: number, level: number) =>
  Float32Array.from({ length: Math.round(RATE * seconds) }, (_, i) => level * Math.SQRT2 * Math.sin(i / 3));

/** Someone says a phrase at `level` (RMS) in a quiet room, then stops, once something listens: a person waits
 * for their turn, and a dialog subscribes again only after the render that asks for the next phrase. */
export async function speak(level = 0.1): Promise<void> {
  await waitFor(() => {
    if (!microphone.listeners.size) throw new Error("nothing listens to the microphone yet");
  });
  act(() => {
    for (const part of [sound(0.4, 0.001), sound(1.2, level), sound(1, 0.001)]) {
      for (let at = 0; at < part.length; at += 2048) {
        for (const listener of [...microphone.listeners]) listener(part.subarray(at, at + 2048));
      }
    }
  });
}
