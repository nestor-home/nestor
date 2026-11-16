/**
 * WebRTC for `pnpm dev` on the mock API: no device films, so the connection Nestor would relay is played here. The
 * admin's own code makes its offer and applies the mock server's answer as it would with Nestor; this peer then
 * sends a test pattern drawn on a canvas for the video, and silence for the sound of a call.
 */

/** A browser's peer connection, as far as the admin uses it, that "receives" what it asked for once answered. */
export class MockPeer extends EventTarget {
  iceGatheringState: RTCIceGatheringState = "complete";
  connectionState: RTCPeerConnectionState = "new";
  localDescription: RTCSessionDescriptionInit | null = null;
  private wants = { video: false, audio: false };
  private stops: (() => void)[] = [];

  addTransceiver(kind: string | MediaStreamTrack): void {
    if (kind === "video") this.wants.video = true;
    else this.wants.audio = true;
  }

  async createOffer(): Promise<RTCSessionDescriptionInit> {
    return { type: "offer", sdp: "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=admin-mock\r\nt=0 0\r\n" };
  }

  async setLocalDescription(description?: RTCSessionDescriptionInit): Promise<void> {
    this.localDescription = description ?? null;
  }

  async setRemoteDescription(): Promise<void> {
    const tracks = [...(this.wants.video ? pattern(this.stops) : []), ...(this.wants.audio ? silence(this.stops) : [])];
    for (const track of tracks) this.dispatchEvent(Object.assign(new Event("track"), { track }));
    this.state("connected");
  }

  close(): void {
    for (const stop of this.stops.splice(0)) stop();
    this.connectionState = "closed"; // closing it oneself fires nothing, as in a browser
  }

  private state(next: RTCPeerConnectionState): void {
    this.connectionState = next;
    this.dispatchEvent(new Event("connectionstatechange"));
  }
}

/** A dithered test pattern with the time running across it, at 15 images a second. */
function pattern(stops: (() => void)[]): MediaStreamTrack[] {
  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 360;
  const context = canvas.getContext("2d");
  if (!context || !canvas.captureStream) return [];
  const bars = ["#1d1b19", "#e8e2d6", "#c4552e", "#7a8a6a", "#d9a441", "#4a4540"];
  const draw = () => {
    const width = canvas.width / bars.length;
    for (const [i, colour] of bars.entries()) {
      context.fillStyle = colour;
      context.fillRect(i * width, 0, width + 1, canvas.height);
    }
    context.fillStyle = "rgba(29, 27, 25, 0.75)";
    context.fillRect(0, canvas.height - 72, canvas.width, 72);
    context.fillStyle = "#f4efe6";
    context.font = "28px ui-monospace, monospace";
    context.fillText(new Date().toLocaleTimeString(), 24, canvas.height - 26);
  };
  draw();
  const timer = setInterval(draw, 1000 / 15);
  const stream = canvas.captureStream(15);
  stops.push(() => {
    clearInterval(timer);
    for (const track of stream.getTracks()) track.stop();
  });
  return stream.getVideoTracks();
}

/** The sound of a quiet room. */
function silence(stops: (() => void)[]): MediaStreamTrack[] {
  if (typeof AudioContext === "undefined") return [];
  const context = new AudioContext();
  const destination = context.createMediaStreamDestination();
  stops.push(() => void context.close());
  return destination.stream.getAudioTracks();
}

/** Installs the mock peer in the browser of `pnpm dev`. */
export function fakePeers(): void {
  globalThis.RTCPeerConnection = MockPeer as unknown as typeof RTCPeerConnection;
}
