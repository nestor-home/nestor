/**
 * What Nestor takes for a voice: 16-bit mono PCM WAV at 16 kHz. The browser captures at its own rate
 * (44.1 or 48 kHz); a phrase is resampled here, then written as a WAV file for one request.
 */

export const VOICE_RATE = 16_000;

/** Zero crossings of the sinc on each side of an output sample: the sharpness of the low-pass. */
const LOBES = 16;

const sinc = (x: number) => (x === 0 ? 1 : Math.sin(Math.PI * x) / (Math.PI * x));
const blackman = (t: number) => 0.42 + 0.5 * Math.cos(Math.PI * t) + 0.08 * Math.cos(2 * Math.PI * t);

/**
 * Mono samples at `from` Hz, at `to` Hz: windowed-sinc interpolation whose low-pass sits just under
 * the lower of the two Nyquist frequencies, so going down filters out what would fold back (aliasing).
 */
export function resample(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return Float32Array.from(input);
  const step = from / to; // input samples per output sample
  const cutoff = Math.min(1, to / from) * 0.95; // of the input's Nyquist frequency
  const span = LOBES / cutoff; // input samples on each side
  const out = new Float32Array(Math.floor((input.length * to) / from));
  for (let i = 0; i < out.length; i++) {
    const centre = i * step;
    const first = Math.max(0, Math.ceil(centre - span));
    const last = Math.min(input.length - 1, Math.floor(centre + span));
    let sum = 0;
    let weight = 0;
    for (let j = first; j <= last; j++) {
      const offset = j - centre;
      const w = sinc(offset * cutoff) * blackman(offset / span);
      sum += (input[j] ?? 0) * w;
      weight += w;
    }
    out[i] = weight ? sum / weight : 0;
  }
  return out;
}

/** A 16-bit mono PCM WAV file of `samples` (in [-1, 1], clipped beyond) at `rate` Hz. */
export function encodeWav(samples: Float32Array, rate: number): ArrayBuffer {
  const bytes = samples.length * 2;
  const buffer = new ArrayBuffer(44 + bytes);
  const view = new DataView(buffer);
  const text = (at: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(at + i, value.charCodeAt(i));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + bytes, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true); // size of the fmt chunk
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true); // bytes per second
  view.setUint16(32, 2, true); // bytes per frame
  view.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  view.setUint32(40, bytes, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i] ?? 0));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

/** A phrase captured at `rate` Hz, as the WAV file Nestor takes. */
export function voiceWav(samples: Float32Array, rate: number): ArrayBuffer {
  return encodeWav(resample(samples, rate, VOICE_RATE), VOICE_RATE);
}
