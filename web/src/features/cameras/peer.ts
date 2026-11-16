/**
 * A session through a satellite, from the browser: one WebRTC connection to Nestor, which relays the device. The
 * browser receives the device's video when it may watch, and for a call sends its microphone and hears the room.
 * The offer leaves once every candidate is gathered (Nestor does not trickle them).
 */
import { api, type MediaPurpose, type MediaSession } from "@/api";
import { MicrophoneError, problemOf } from "@/lib/audio/microphone";

/** How long candidates may take to gather before the offer leaves with those found. */
const GATHERING_MS = 3_000;

/** This browser has no WebRTC. */
export class Unsupported extends Error {
  constructor() {
    super("no WebRTC in this browser");
    this.name = "Unsupported";
  }
}

export interface Live {
  session: MediaSession;
  /** What the device sends: its video, its sound, or both. */
  stream: MediaStream;
  /** Silences one's own microphone (a call), or lets it be heard again. */
  mute(muted: boolean): void;
  /** Ends it, here and on Nestor; `leaving` when the page closes. */
  close(leaving?: boolean): void;
}

/** Opens the microphone for a call, with the echo cancelled: the room hears itself otherwise. */
async function microphone(): Promise<MediaStream> {
  if (!window.isSecureContext) throw new MicrophoneError("insecure");
  if (!navigator.mediaDevices?.getUserMedia) throw new MicrophoneError("unsupported");
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (error) {
    throw new MicrophoneError(problemOf(error));
  }
}

function gathered(peer: RTCPeerConnection): Promise<void> {
  if (peer.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer);
      peer.removeEventListener("icegatheringstatechange", check);
      resolve();
    };
    const check = () => {
      if (peer.iceGatheringState === "complete") done();
    };
    const timer = setTimeout(done, GATHERING_MS);
    peer.addEventListener("icegatheringstatechange", check);
  });
}

/**
 * Watches `device` (`view`) or calls through it (`call`, with its video when `video`). `onEnd` hears the connection
 * end on its own (the device left, Nestor ended it).
 */
export async function connect(
  device: string,
  purpose: MediaPurpose,
  { video, onEnd }: { video: boolean; onEnd: () => void },
): Promise<Live> {
  if (typeof RTCPeerConnection === "undefined") throw new Unsupported();
  const mic = purpose === "call" ? await microphone() : null;
  const peer = new RTCPeerConnection();
  const stream = new MediaStream();
  const release = () => {
    peer.close();
    for (const track of mic?.getTracks() ?? []) track.stop();
  };
  peer.addEventListener("track", (event) => stream.addTrack(event.track));
  if (video) peer.addTransceiver("video", { direction: "recvonly" });
  for (const track of mic?.getAudioTracks() ?? []) {
    peer.addTransceiver(track, { direction: "sendrecv", streams: [mic as MediaStream] });
  }
  let session: MediaSession;
  try {
    await peer.setLocalDescription(await peer.createOffer());
    await gathered(peer);
    session = await api.openMediaSession(device, purpose, peer.localDescription?.sdp ?? "");
  } catch (error) {
    release();
    throw error;
  }
  let open = true;
  const close = (leaving = false) => {
    if (!open) return;
    open = false;
    release();
    void api.closeMediaSession(session.session_id, leaving).catch(() => undefined); // it ends at its limit anyway
  };
  try {
    await peer.setRemoteDescription({ type: session.type as RTCSdpType, sdp: session.sdp });
  } catch (error) {
    close();
    throw error;
  }
  peer.addEventListener("connectionstatechange", () => {
    if (open && (peer.connectionState === "failed" || peer.connectionState === "closed")) {
      close();
      onEnd();
    }
  });
  return {
    session,
    stream,
    mute: (muted) => {
      for (const track of mic?.getAudioTracks() ?? []) track.enabled = !muted;
    },
    close,
  };
}
