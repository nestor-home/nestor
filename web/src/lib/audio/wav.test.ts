import { describe, expect, it } from "vitest";
import { encodeWav, resample, VOICE_RATE, voiceWav } from "./wav";

const tone = (hz: number, rate: number, seconds: number, amplitude = 0.5) =>
  Float32Array.from(
    { length: Math.round(rate * seconds) },
    (_, i) => amplitude * Math.sin((2 * Math.PI * hz * i) / rate),
  );

/** The RMS of the middle of a signal, away from the edges a filter cannot see past. */
const middleRms = (s: Float32Array) => {
  const part = s.subarray(Math.floor(s.length * 0.2), Math.floor(s.length * 0.8));
  return Math.sqrt(part.reduce((sum, x) => sum + x * x, 0) / part.length);
};

describe("resampling to 16 kHz", () => {
  it("keeps the duration", () => {
    expect(resample(new Float32Array(48_000), 48_000, VOICE_RATE)).toHaveLength(16_000);
    expect(resample(new Float32Array(44_100), 44_100, VOICE_RATE)).toHaveLength(16_000);
  });

  it("keeps a voice-range tone, its pitch and its loudness", () => {
    const out = resample(tone(440, 48_000, 0.5), 48_000, VOICE_RATE);
    const expected = tone(440, VOICE_RATE, 0.5);
    const middle = (s: Float32Array) => s.subarray(2000, 6000);
    const error = middle(out).reduce((max, x, i) => Math.max(max, Math.abs(x - (middle(expected)[i] ?? 0))), 0);
    expect(error).toBeLessThan(0.01);
  });

  it("filters out what 16 kHz cannot hold instead of folding it into the voice", () => {
    // 12 kHz would come back as a 4 kHz whistle without the low-pass
    expect(middleRms(resample(tone(12_000, 48_000, 0.5), 48_000, VOICE_RATE))).toBeLessThan(0.01);
    expect(middleRms(resample(tone(10_000, 44_100, 0.5), 44_100, VOICE_RATE))).toBeLessThan(0.01);
  });

  it("leaves audio already at 16 kHz as it is", () => {
    const input = tone(300, VOICE_RATE, 0.1);
    expect(resample(input, VOICE_RATE, VOICE_RATE)).toEqual(input);
  });
});

describe("the WAV file", () => {
  it("is 16-bit mono PCM at the given rate", () => {
    const view = new DataView(encodeWav(new Float32Array(10), VOICE_RATE));
    const text = (at: number) => String.fromCharCode(...new Uint8Array(view.buffer, at, 4));
    expect([text(0), text(8), text(12), text(36)]).toEqual(["RIFF", "WAVE", "fmt ", "data"]);
    expect(view.getUint32(4, true)).toBe(36 + 20);
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint32(28, true)).toBe(32_000);
    expect(view.getUint16(32, true)).toBe(2);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(20);
    expect(view.byteLength).toBe(44 + 20);
  });

  it("writes the samples at full scale, clipping what goes beyond", () => {
    const view = new DataView(encodeWav(Float32Array.from([0, 0.5, -0.5, 1, -1, 1.7, -3]), VOICE_RATE));
    const samples = Array.from({ length: 7 }, (_, i) => view.getInt16(44 + i * 2, true));
    expect(samples).toEqual([0, 16383, -16384, 32767, -32768, 32767, -32768]);
  });

  it("turns a capture at 48 kHz into a phrase at 16 kHz", () => {
    const view = new DataView(voiceWav(tone(200, 48_000, 1), 48_000));
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint32(40, true)).toBe(16_000 * 2);
  });
});
