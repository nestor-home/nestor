/**
 * The microphone of `pnpm dev` on the mock API: a fake one, so a voice can be recorded anywhere,
 * end to end tests included. It "speaks" 1.4 s of shaped noise, then is silent for 1.1 s, over and
 * over: long enough for a phrase, a pause long enough to end it.
 */
const SPEECH_S = 1.4;
const CYCLE_S = 2.5;

function voice(context: AudioContext): AudioBuffer {
  const buffer = context.createBuffer(1, Math.round(context.sampleRate * CYCLE_S), context.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i++) {
    const t = i / context.sampleRate;
    const envelope = t < SPEECH_S ? Math.sin((Math.PI * t) / SPEECH_S) ** 0.3 : 0;
    const syllables = 0.6 + 0.4 * Math.sin(2 * Math.PI * 4 * t);
    data[i] = (Math.random() * 2 - 1) * (0.25 * envelope * syllables + 0.0005);
  }
  return buffer;
}

export function fakeMicrophone(): void {
  const media = navigator.mediaDevices;
  if (!media) return;
  media.getUserMedia = async (constraints?: MediaStreamConstraints) => {
    if (!constraints?.audio || constraints.video) throw new DOMException("audio only", "NotSupportedError");
    const context = new AudioContext();
    const destination = context.createMediaStreamDestination();
    const source = context.createBufferSource();
    source.buffer = voice(context);
    source.loop = true;
    source.connect(destination);
    source.start();
    for (const track of destination.stream.getTracks()) {
      const stop = track.stop.bind(track);
      track.stop = () => {
        stop();
        void context.close();
      };
    }
    return destination.stream;
  };
  media.enumerateDevices = async () =>
    [
      { deviceId: "mock-microphone", groupId: "mock", kind: "audioinput", label: "Mock microphone" },
      { deviceId: "mock-headset", groupId: "mock", kind: "audioinput", label: "Mock headset" },
    ].map((d) => ({ ...d, toJSON: () => d })) as MediaDeviceInfo[];
}
