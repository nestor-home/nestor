import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { db } from "@/mocks/db";
import { MockPeer } from "@/mocks/peer";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

/** jsdom has neither WebRTC nor media streams: the mock peer stands for the browser's, a stream only holds tracks. */
class Stream {
  tracks: MediaStreamTrack[] = [];
  addTrack(track: MediaStreamTrack) {
    this.tracks.push(track);
  }
  getTracks() {
    return this.tracks;
  }
  getAudioTracks() {
    return this.tracks;
  }
}

/** The browser's microphone: one track, which a call mutes and stops. */
const mic = { enabled: true, stopped: false, stop: () => {} } as unknown as MediaStreamTrack & { stopped: boolean };
const getUserMedia = vi.fn();
/** The object URLs made for pictures, and those given back. */
const created: string[] = [];
const revoked: string[] = [];

/** What the admin asks of the devices (opening, ending, pictures), as `METHOD path`. */
function sent(): string[] {
  const seen: string[] = [];
  server.events.on("request:start", ({ request }) => {
    const path = new URL(request.url).pathname;
    if (path.includes("/media") && request.method !== "GET") seen.push(`${request.method} ${path}`);
  });
  return seen;
}

/** The sessions the server opened, by id, in the order it answered. */
function opened(): string[] {
  const ids: string[] = [];
  server.events.on("response:mocked", async ({ request, response }) => {
    if (request.method !== "POST" || !new URL(request.url).pathname.endsWith("/media/sessions")) return;
    ids.push(((await response.clone().json()) as { session_id: string }).session_id);
  });
  return ids;
}

beforeEach(() => {
  vi.stubGlobal("RTCPeerConnection", MockPeer);
  vi.stubGlobal("MediaStream", Stream);
  vi.stubGlobal("isSecureContext", true);
  Object.assign(mic, { enabled: true, stopped: false, stop: () => Object.assign(mic, { stopped: true }) });
  getUserMedia.mockReset().mockResolvedValue(Object.assign(new Stream(), { tracks: [mic] }));
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
  created.length = 0;
  revoked.length = 0;
  URL.createObjectURL = () => {
    created.push(`blob:picture-${created.length}`);
    return created.at(-1) as string;
  };
  URL.revokeObjectURL = (url) => void revoked.push(url);
});
afterEach(() => {
  vi.unstubAllGlobals();
  server.events.removeAllListeners();
});

/** The house, where one watches and calls: its "Watch and call" part lists the devices one may use. */
async function deviceRow(name: string): Promise<HTMLElement> {
  const media = await screen.findByRole("region", { name: /^Watch and call/ });
  const label = await within(media).findByText(name, { selector: "p" });
  const row = label.closest("li");
  if (!row) throw new Error(`${name} is a row`);
  return row;
}

describe("watching and calling through a device", () => {
  it("offers on each device what it allows, and nothing through one that is offline", async () => {
    renderApp("/house");
    const living = await deviceRow("Living room Reachy");
    for (const action of ["View", "Call", "picture"]) {
      expect(within(living).getByRole("button", { name: new RegExp(action) })).toBeEnabled();
    }
    const office = await deviceRow("reachy-office");
    expect(within(office).getByText("camera switched off")).toBeVisible();
    expect(within(office).getByRole("button", { name: /Call/ })).toBeDisabled();
    const bedroom = await deviceRow("Jules's speaker"); // it does not film
    expect(within(bedroom).queryByRole("button", { name: /View|picture/ })).not.toBeInTheDocument();
    expect(within(bedroom).getByRole("button", { name: /Call/ })).toBeEnabled();
  });

  it("says why a camera does not film now, under its privacy rules", async () => {
    const living = db.satellites.find((s) => s.id === "reachy-living-room");
    if (!living) throw new Error("fixture changed");
    // the tests run on a Friday at 18:30, in the household's time once it lives in the test's time zone
    (db.config.document.persona as { timezone: string }).timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    living.access.privacy.quiet = [{ days: ["fri"], start: "18:00", end: "19:00" }];
    const { unmount } = renderApp("/house");
    const row = await deviceRow("Living room Reachy");
    expect(within(row).getByText("off during quiet hours")).toBeVisible();
    expect(within(row).queryByRole("button", { name: /View|picture/ })).not.toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /Call/ })).toBeEnabled();
    unmount();

    living.access.privacy.quiet = [{ days: ["fri"], start: "19:00", end: "18:00" }]; // from 19:00 into Saturday
    living.access.privacy.off_when_home = true; // Mathis is home
    renderApp("/house");
    const again = await deviceRow("Living room Reachy");
    expect(within(again).getByText("off while someone is home")).toBeVisible();
    expect(within(again).queryByRole("button", { name: /View/ })).not.toBeInTheDocument();
  });

  it("is reached from a room too, over the room's sheet", async () => {
    const requests = sent();
    const user = userEvent.setup();
    renderApp("/house");
    const rooms = await screen.findByRole("region", { name: /^The rooms/ });
    await user.click(await within(rooms).findByRole("button", { name: /^Living room/ }));
    const room = await screen.findByRole("dialog", { name: "Living room" });
    await user.click(await within(room).findByRole("button", { name: "View Living room Reachy" }));
    const dialog = await screen.findByRole("dialog", { name: "Living room Reachy, live" });
    expect(await within(dialog).findByText(/s left/)).toBeVisible();
    expect(requests).toContain("POST /api/v1/satellites/reachy-living-room/media/sessions");
  });

  it("watches a device live, and ends the session when the dialog closes", async () => {
    const requests = sent();
    const sessions = opened();
    const user = userEvent.setup();
    renderApp("/house");
    await user.click(within(await deviceRow("Living room Reachy")).getByRole("button", { name: /View/ }));
    const dialog = await screen.findByRole("dialog", { name: "Living room Reachy, live" });
    expect(within(dialog).getByText("What it films in “living room”, until you close.")).toBeVisible();
    expect(await within(dialog).findByText(/^10 min 00 s left|^9 min 5\d s left/)).toBeVisible();
    expect(getUserMedia).not.toHaveBeenCalled(); // watching never opens the microphone
    await user.click(within(dialog).getAllByRole("button", { name: "Close" }).at(-1) as HTMLElement);
    expect(requests).toContain("POST /api/v1/satellites/reachy-living-room/media/sessions");
    // its own session, whatever an earlier test's still ends meanwhile
    await waitFor(() => expect(requests).toContain(`DELETE /api/v1/media/sessions/${sessions[0]}`));
  });

  it("calls through a device: the microphone mutes, and hanging up ends the session and releases it", async () => {
    const requests = sent();
    const user = userEvent.setup();
    renderApp("/house");
    await user.click(within(await deviceRow("Jules's speaker")).getByRole("button", { name: /Call/ }));
    const dialog = await screen.findByRole("dialog", { name: "Call through Jules's speaker" });
    expect(await within(dialog).findByText(/you hear “bedroom”/)).toBeVisible(); // it does not film
    await user.click(within(dialog).getByRole("button", { name: "Mute" }));
    expect(mic.enabled).toBe(false);
    expect(within(dialog).getByRole("button", { name: "Unmute" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(dialog).getByRole("button", { name: "Hang up" }));
    await waitFor(() => expect(requests.at(-1)).toMatch(/^DELETE \/api\/v1\/media\/sessions\//));
    expect(mic.stopped).toBe(true);
  });

  it("says why a call cannot start when the browser refuses the microphone, without opening a session", async () => {
    const requests = sent();
    getUserMedia.mockRejectedValue(new DOMException("no", "NotAllowedError"));
    const user = userEvent.setup();
    renderApp("/house");
    await user.click(within(await deviceRow("Living room Reachy")).getByRole("button", { name: /Call/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("The browser refuses the microphone");
    expect(requests.filter((r) => r.startsWith("POST"))).toEqual([]); // a session left by an earlier test may still end
  });

  it("shows the server's refusal, and tries again", async () => {
    server.use(
      http.post(
        "/api/v1/satellites/:id/media/sessions",
        () =>
          HttpResponse.json(
            {
              error: {
                code: "media_offline",
                message_id: "error-media-offline",
                args: {},
                message: "This device is not connected, or it did not answer.",
              },
            },
            { status: 409 },
          ),
        { once: true },
      ),
    );
    const user = userEvent.setup();
    renderApp("/house");
    await user.click(within(await deviceRow("Living room Reachy")).getByRole("button", { name: /View/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This device is not connected");
    await user.click(within(dialog).getByRole("button", { name: "Try again" }));
    expect(await within(dialog).findByText(/s left/)).toBeVisible();
  });

  it("ends a session at its longest duration", async () => {
    server.use(
      http.post("/api/v1/satellites/:id/media/sessions", () =>
        HttpResponse.json({ session_id: "s-short", sdp: "v=0", type: "answer", video: true, audio: false, max_s: 1 }),
      ),
    );
    const user = userEvent.setup();
    renderApp("/house");
    await user.click(within(await deviceRow("Living room Reachy")).getByRole("button", { name: /View/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("The session ended.", {}, { timeout: 4000 })).toBeVisible();
    expect(within(dialog).queryByText(/s left/)).not.toBeInTheDocument();
  });

  it("takes a picture on demand, to look at and download under the server's name, and lets it go on closing", async () => {
    const user = userEvent.setup();
    renderApp("/house");
    await user.click(within(await deviceRow("Living room Reachy")).getByRole("button", { name: /picture/i }));
    const dialog = await screen.findByRole("dialog", { name: "Picture from Living room Reachy" });
    expect(
      await within(dialog).findByRole("img", { name: "What Living room Reachy films in “living room”" }),
    ).toHaveAttribute("src", "blob:picture-0");
    expect(within(dialog).getByRole("link", { name: /Download/ })).toHaveAttribute(
      "download",
      expect.stringMatching(/^living room-\d{8}-\d{6}\.jpg$/),
    );
    await user.click(within(dialog).getAllByRole("button", { name: "Close" }).at(-1) as HTMLElement);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(revoked).toEqual(created);
  });

  it("keeps no picture that arrives after its dialog closed", async () => {
    const requests = sent();
    const user = userEvent.setup();
    renderApp("/house");
    await user.click(within(await deviceRow("Living room Reachy")).getByRole("button", { name: /picture/i }));
    const dialog = await screen.findByRole("dialog", { name: "Picture from Living room Reachy" });
    await waitFor(() => expect(requests).toContain("POST /api/v1/satellites/reachy-living-room/media/snapshot"));
    await user.click(within(dialog).getAllByRole("button", { name: "Close" }).at(-1) as HTMLElement);
    await new Promise((resolve) => setTimeout(resolve, 900)); // the mock takes 600 ms to answer
    expect(revoked).toEqual(created);
  });
});
