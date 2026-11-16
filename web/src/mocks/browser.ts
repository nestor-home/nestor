import { setupWorker } from "msw/browser";
import { load } from "./db";
import { handlers, liveJournal } from "./handlers";
import { fakeMicrophone } from "./microphone";
import { fakePeers } from "./peer";

/** Starts the mock API in the browser (`pnpm dev` without NESTOR_API). */
export async function startMocks(): Promise<void> {
  load();
  fakeMicrophone();
  fakePeers();
  await setupWorker(liveJournal(), ...handlers).start({ onUnhandledFrame: "bypass", quiet: true });
}
