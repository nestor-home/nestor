/**
 * Runs on the audio thread: hands the microphone's samples to the page, about 40 ms at a time, as
 * they come (the first channel; capture is mono).
 */

declare abstract class AudioWorkletProcessor {
  readonly port: MessagePort;
  abstract process(inputs: Float32Array[][]): boolean;
}
declare function registerProcessor(name: string, processor: new () => AudioWorkletProcessor): void;

const CHUNK = 2048;

class Capture extends AudioWorkletProcessor {
  private buffer = new Float32Array(CHUNK);
  private filled = 0;

  process(inputs: Float32Array[][]): boolean {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    let at = 0;
    while (at < channel.length) {
      const take = Math.min(CHUNK - this.filled, channel.length - at);
      this.buffer.set(channel.subarray(at, at + take), this.filled);
      this.filled += take;
      at += take;
      if (this.filled === CHUNK) {
        this.port.postMessage(this.buffer, [this.buffer.buffer]);
        this.buffer = new Float32Array(CHUNK);
        this.filled = 0;
      }
    }
    return true;
  }
}

registerProcessor("nestor-capture", Capture);
