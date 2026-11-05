import { describe, expect, it } from "vitest";
import { Endpointer, hearing, loudness, silence, type Utterance } from "./endpoint";

const RATE = 16_000;

/** A steady sound of `level` RMS: a low hum standing for a room or a voice. */
const sound = (seconds: number, level: number) =>
  Float32Array.from({ length: Math.round(RATE * seconds) }, (_, i) => level * Math.SQRT2 * Math.sin(i / 3));
const quiet = (seconds: number) => sound(seconds, 0.001);
const voice = (seconds: number) => sound(seconds, 0.1);

/** Feeds the parts in browser-sized chunks (128 samples, as an AudioWorklet does). */
function listen(...parts: Float32Array[]) {
  const heard: Utterance[] = [];
  const endpointer = new Endpointer(RATE, (u) => heard.push(u));
  const feed = (part: Float32Array) => {
    for (let at = 0; at < part.length; at += 128) endpointer.push(part.subarray(at, at + 128));
  };
  for (const part of parts) feed(part);
  return { heard, endpointer, feed };
}

describe("finding where a phrase ends", () => {
  it("hears one phrase once the speaker has been silent for 0.8 s", () => {
    const { heard, feed } = listen(quiet(0.5), voice(1.2), quiet(0.7));
    expect(heard).toHaveLength(0);
    feed(quiet(0.2));
    expect(heard).toHaveLength(1);
  });

  it("keeps the phrase with a little air around it and drops the rest of the silence", () => {
    const { heard } = listen(quiet(1), voice(1.2), quiet(1.5));
    const [phrase] = heard;
    expect(phrase?.speechMs).toBeGreaterThanOrEqual(1180);
    expect(phrase?.speechMs).toBeLessThanOrEqual(1240);
    const seconds = (phrase?.samples.length ?? 0) / RATE;
    expect(seconds).toBeGreaterThan(1.5); // 0.2 s before, 0.2 s after
    expect(seconds).toBeLessThan(1.7);
  });

  it("does not cut a phrase at a short pause between words", () => {
    const { heard } = listen(quiet(0.5), voice(0.8), quiet(0.5), voice(0.8), quiet(1));
    expect(heard).toHaveLength(1);
    expect(heard[0]?.speechMs).toBeGreaterThan(2000);
  });

  it("ignores a click or a cough", () => {
    const { heard } = listen(quiet(0.5), voice(0.15), quiet(1.5));
    expect(heard).toHaveLength(0);
  });

  it("hears two phrases said one after the other", () => {
    const { heard } = listen(quiet(0.5), voice(1), quiet(1), voice(1.5), quiet(1));
    expect(heard).toHaveLength(2);
  });

  it("ends a phrase that never stops after 15 s", () => {
    const { heard } = listen(quiet(0.5), voice(16));
    expect(heard).toHaveLength(1);
  });

  it("needs speech to stand out of a noisy room", () => {
    const room = (s: number) => sound(s, 0.04);
    expect(listen(room(1), sound(1, 0.08), room(1.5)).heard).toHaveLength(0);
    expect(listen(room(1), sound(1, 0.3), room(1.5)).heard).toHaveLength(1);
  });

  it("forgets a phrase in progress when reset", () => {
    const { heard, endpointer, feed } = listen(quiet(0.5), voice(1));
    endpointer.reset();
    feed(quiet(1));
    expect(heard).toHaveLength(0);
  });

  it("follows the level, for a mouth that opens with the voice", () => {
    const { endpointer, feed } = listen(quiet(0.5));
    expect(loudness(endpointer.level)).toBeLessThan(0.05);
    feed(voice(0.1));
    expect(loudness(endpointer.level)).toBeGreaterThan(0.6);
    expect(loudness(1)).toBe(1);
  });
});

describe("whether a voice comes through", () => {
  it("is clear when loud enough over a calm room", () => {
    expect(hearing({ peak: 0.1, floor: 0.001 })).toBe("clear");
  });

  it("is too quiet when the voice barely reaches the microphone", () => {
    expect(hearing({ peak: 0.01, floor: 0.0005 })).toBe("quiet");
  });

  it("is too noisy when the room is loud or the voice hardly stands out", () => {
    expect(hearing({ peak: 0.3, floor: 0.05 })).toBe("noisy");
    expect(hearing({ peak: 0.05, floor: 0.01 })).toBe("noisy");
  });

  it("blames the room or the microphone when nothing is heard", () => {
    expect(silence(0.05)).toBe("noisy");
    expect(silence(0.0005)).toBe("quiet");
  });
});
