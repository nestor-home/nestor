/** The files of the mock journal, made here: a dithered picture, and a short hum standing for a voice message. */

const PICTURE =
  "iVBORw0KGgoAAAANSUhEUgAAAKAAAABkCAIAAACO1KzYAAACY0lEQVR42u2cS2rEMBBE6xohOUYOlFPnCrPNwgfIYiAEYxh/JLmr9KBpvG7V85Nsz2j5efzVx/tbp2v6if6si9f6v8ABRUZXXcwxm/U0gitktFReBYt53k1zMBlt42Dm6Mi68G52XgWLGa7dvDYmGF+0cTBzdOdeeDc7o4LFPO86OXjCfW8XBzPHVO6Fd7MzKljM8251B+MLJwfT72VdeDc7o4LFPO9WdDDedXIwvQ7rwrXZGRUs5nm3ioNh0cnB9JqsC++GEwyLed69k2BYdHIwvT7rwrtTOJie5N3RBMOik4PpXqwL7+JgWDTz7giCYdHJwXRf1mXt3e+vz53XrToOHtfbrtyqP2t17eLdXgSP9G7X1Y0i2Ne7RVa3+B5b1ufdMd7FwSEEb3q3uYMHl0zPuzh452lNvufdG1fX6NmWrJ8zj/EuDjYm+KV3mzj4xpLpc2YcvDNh7KIPsO74TkmL8/tddtE4+Kp3Tzu4SGnxfL87rYOP3vlx8AHWvb7l6OXgMayzi8bBbbz70sHFS6bfVU1F8BUL4OADrHt9y9HSweNZx8E7WU8muIl3Nx1sVDL9v7h4gludxPhlg/1vF3o5mN8uWKRTsOj1bPkMwfAXnE4xzWzWhXez0yn4y/NuXwfTSyVVTDObdd3oXfqAdAr+8rzb3sH0skkV08xmXXg3O53ibpZdgsXspIoJZrMuvJudVMEiDoZF46SKCWazLrybnVTB4uwOplsnVUwwm3Xh3eykChZndDA9JqligvkE493gpAoWZ3EwPTKpYoI4GO8aJ1WwiIPpxukUdzMcDLvGSf0FDLyuG9y4w9wAAAAASUVORK5CYII=";

/** A PNG: the photo someone sent. */
export function picture(): Uint8Array {
  return Uint8Array.from(atob(PICTURE), (c) => c.charCodeAt(0));
}

/** A WAV of `seconds` of a soft hum, mono 16-bit at 16 kHz: what a voice message plays in the mock. */
export function recording(seconds = 2): Uint8Array {
  const rate = 16_000;
  const samples = Math.round(rate * seconds);
  const view = new DataView(new ArrayBuffer(44 + samples * 2));
  const text = (at: number, value: string) => {
    for (const [i, c] of [...value].entries()) view.setUint8(at + i, c.charCodeAt(0));
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + samples * 2, true);
  text(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, samples * 2, true);
  for (let i = 0; i < samples; i++) {
    const t = i / rate;
    const swell = Math.sin(Math.PI * Math.min(1, t / seconds)) * 0.25;
    view.setInt16(
      44 + i * 2,
      Math.round(swell * 32767 * Math.sin(2 * Math.PI * (180 + 40 * Math.sin(t * 3)) * t)),
      true,
    );
  }
  return new Uint8Array(view.buffer);
}
