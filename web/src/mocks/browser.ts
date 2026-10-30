import { setupWorker } from "msw/browser";
import { load } from "./db";
import { handlers, liveJournal } from "./handlers";

/** Starts the mock API in the browser (`pnpm dev` without NESTOR_API). */
export async function startMocks(): Promise<void> {
  load();
  await setupWorker(liveJournal(), ...handlers).start({ onUnhandledFrame: "bypass", quiet: true });
}
