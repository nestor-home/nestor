/**
 * When someone starts and stops speaking, from the microphone's energy alone: no button to press.
 * Audio is cut in 20 ms frames; speech starts once frames stay well above the background noise
 * (tracked while nobody speaks), and ends after 0.8 s under it. The utterance keeps a little before
 * and after the speech, and drops the rest of the silence.
 */

export interface EndpointOptions {
  frameMs: number;
  calibrateMs: number; // listened to first, for the background alone
  startFactor: number; // speech is this many times louder than the background (×4 ≈ +12 dB)
  minStart: number; // never start under this level (RMS, full scale = 1)
  startMs: number; // how long it stays above before it counts as speech
  silenceMs: number; // how long under it ends an utterance
  minSpeechMs: number; // shorter is a click or a cough, not a phrase
  preRollMs: number; // kept before the speech
  tailMs: number; // kept after the speech
  maxMs: number; // an utterance ends there whatever
}

export const ENDPOINTING: EndpointOptions = {
  frameMs: 20,
  calibrateMs: 200,
  startFactor: 4,
  minStart: 0.006,
  startMs: 60,
  silenceMs: 800,
  minSpeechMs: 300,
  preRollMs: 200,
  tailMs: 200,
  maxMs: 15_000,
};

export interface Utterance {
  samples: Float32Array;
  rate: number;
  speechMs: number; // from the first to the last voiced frame
  peak: number; // the loudest frame (RMS)
  floor: number; // the background before it (RMS)
}

const rms = (frame: Float32Array) => {
  let sum = 0;
  for (const s of frame) sum += s * s;
  return Math.sqrt(sum / (frame.length || 1));
};

/** A level for eyes (a mouth that opens): -60 dBFS and under is 0, -20 dBFS and over is 1. */
export function loudness(level: number): number {
  if (level <= 0) return 0;
  return Math.max(0, Math.min(1, (20 * Math.log10(level) + 60) / 40));
}

export class Endpointer {
  private readonly options: EndpointOptions;
  private readonly frameSize: number;
  private partial: Float32Array;
  private filled = 0;
  private background: number | null = null;
  private calibrating: number[] = [];
  private recent: Float32Array[] = []; // the frames before speech: pre-roll and the start being confirmed
  private above = 0; // consecutive frames above the start level
  private speech: Float32Array[] | null = null;
  private threshold = 0;
  private lastVoiced = 0; // index in `speech` of the last frame above the end level
  private firstVoiced = 0;
  private peak = 0;
  private quietMs = 0;
  /** the last frame's level (RMS) */
  level = 0;

  constructor(
    readonly rate: number,
    private readonly onUtterance: (utterance: Utterance) => void,
    options: Partial<EndpointOptions> = {},
  ) {
    this.options = { ...ENDPOINTING, ...options };
    this.frameSize = Math.round((rate * this.options.frameMs) / 1000);
    this.partial = new Float32Array(this.frameSize);
  }

  /** The background noise as tracked while nobody speaks (RMS). */
  get floor(): number {
    return this.background ?? 0;
  }

  /** Whether someone is speaking right now. */
  get speaking(): boolean {
    return this.speech !== null;
  }

  /** Feeds captured samples, in chunks of any size. */
  push(chunk: Float32Array): void {
    let at = 0;
    while (at < chunk.length) {
      const take = Math.min(this.frameSize - this.filled, chunk.length - at);
      this.partial.set(chunk.subarray(at, at + take), this.filled);
      this.filled += take;
      at += take;
      if (this.filled === this.frameSize) {
        this.frame(this.partial);
        this.partial = new Float32Array(this.frameSize);
        this.filled = 0;
      }
    }
  }

  /** Forgets any utterance in progress (the next one starts from silence); keeps the background. */
  reset(): void {
    this.speech = null;
    this.recent = [];
    this.above = 0;
    this.filled = 0;
  }

  private frames(ms: number): number {
    return Math.max(1, Math.round(ms / this.options.frameMs));
  }

  private frame(frame: Float32Array): void {
    const level = rms(frame);
    this.level = level;
    if (this.calibrating.length < this.frames(this.options.calibrateMs)) {
      this.calibrating.push(level);
      this.background = this.calibrating.reduce((a, b) => a + b, 0) / this.calibrating.length;
      this.recent.push(frame);
      return;
    }
    if (this.speech) this.continueSpeech(frame, level);
    else this.waitForSpeech(frame, level);
  }

  private startLevel(): number {
    return Math.max(this.options.minStart, this.floor * this.options.startFactor);
  }

  private waitForSpeech(frame: Float32Array, level: number): void {
    const o = this.options;
    if (level > this.startLevel()) this.above++;
    else {
      this.above = 0;
      // the background: follows quiet frames down quickly, rises slowly (about 4 dB a second)
      const background = this.floor;
      this.background = level < background ? background * 0.5 + level * 0.5 : Math.min(level, background * 1.01);
    }
    this.recent.push(frame);
    const keep = this.frames(o.preRollMs) + this.above;
    if (this.recent.length > keep) this.recent.splice(0, this.recent.length - keep);
    if (this.above >= this.frames(o.startMs)) {
      this.threshold = this.startLevel();
      this.speech = this.recent;
      this.recent = [];
      this.firstVoiced = this.speech.length - this.above;
      this.lastVoiced = this.speech.length - 1;
      this.peak = level;
      this.quietMs = 0;
      this.above = 0;
    }
  }

  private continueSpeech(frame: Float32Array, level: number): void {
    const o = this.options;
    const speech = this.speech as Float32Array[];
    speech.push(frame);
    this.peak = Math.max(this.peak, level);
    if (level > this.threshold * 0.5) {
      this.lastVoiced = speech.length - 1;
      this.quietMs = 0;
    } else this.quietMs += o.frameMs;
    const lasted = (speech.length - this.firstVoiced) * o.frameMs;
    if (this.quietMs < o.silenceMs && lasted < o.maxMs) return;
    this.speech = null;
    const speechMs = (this.lastVoiced - this.firstVoiced + 1) * o.frameMs;
    if (speechMs < o.minSpeechMs) return;
    const end = Math.min(speech.length, this.lastVoiced + 1 + this.frames(o.tailMs));
    const kept = speech.slice(0, end);
    const samples = new Float32Array(kept.length * this.frameSize);
    kept.forEach((f, i) => {
      samples.set(f, i * this.frameSize);
    });
    this.onUtterance({ samples, rate: this.rate, speechMs, peak: this.peak, floor: this.floor });
  }
}

export type Hearing = "clear" | "quiet" | "noisy";

/** Whether a voice comes through well enough to record: loud enough, and clearly over the noise. */
export function hearing({ peak, floor }: Pick<Utterance, "peak" | "floor">): Hearing {
  if (floor > 0.03 || peak < floor * 6) return "noisy";
  if (peak < 0.015) return "quiet";
  return "clear";
}

/** Nobody heard for a while: the room is too loud for speech to stand out, or the microphone too quiet. */
export function silence(floor: number): Exclude<Hearing, "clear"> {
  return floor > 0.03 ? "noisy" : "quiet";
}
