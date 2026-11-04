import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { db } from "@/mocks/db";
import { recordingsInProgress } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { microphone, speak } from "@/test/microphone";
import { renderApp } from "@/test/render";

vi.mock("@/lib/audio/microphone", () => import("@/test/microphone").then((m) => m.module()));

beforeEach(() => microphone.reset());

async function openRecording(person: string, button: RegExp) {
  const user = userEvent.setup();
  const view = renderApp(`/people/${person}`);
  await user.click(await screen.findByRole("button", { name: button }));
  const dialog = await screen.findByRole("dialog");
  return { user, dialog, ...view };
}

/** Through consent and the microphone, up to the first phrase. */
async function toPhrases(person = "jules", button = /^Record their voice/) {
  const opened = await openRecording(person, button);
  const { user, dialog } = opened;
  await user.click(within(dialog).getByRole("button", { name: "Start" }));
  await within(dialog).findByText("Say “Hello Richie” to try the microphone.");
  await speak();
  await within(dialog).findByText("I can hear you well.");
  await user.click(within(dialog).getByRole("button", { name: "Continue" }));
  await within(dialog).findByText("“Nestor, turn on the lights in the living room.”");
  return opened;
}

describe("a person's voice on their page", () => {
  it("says when it was recorded and what was learned since", async () => {
    renderApp("/people/mathis");
    expect(await screen.findByText(/^Recorded/)).toBeInTheDocument();
    expect(screen.getByText(/12 voiceprints learned since, the last/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Learn over time" })).toBeChecked();
  });

  it("shows another account's voice without offering to change it", async () => {
    renderApp("/people/lea");
    expect(await screen.findByText("Not recorded yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Record/ })).not.toBeInTheDocument();
  });

  it("points the owner to the configuration when voices are off", async () => {
    server.use(
      http.get("/api/v1/household/people/:id/voice", () =>
        HttpResponse.json(
          { error: { code: "voices_off", message_id: "error-voices-off", args: {}, message: "Voices are off." } },
          { status: 404 },
        ),
      ),
    );
    renderApp("/people/mathis");
    expect(await screen.findByText("Voice recognition is off.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Configuration › Voices" })).toHaveAttribute("href", "/config/voices");
  });

  it("stops and resumes learning over time", async () => {
    const user = userEvent.setup();
    renderApp("/people/mathis");
    await user.click(await screen.findByRole("switch", { name: "Learn over time" }));
    expect(await screen.findByText("No longer learns over time.")).toBeInTheDocument();
    expect(db.voices.mathis?.learning).toBe(false);
  });

  it("forgets what was learned and keeps the recording", async () => {
    const user = userEvent.setup();
    renderApp("/people/mathis");
    await user.click(await screen.findByRole("button", { name: "Forget what was learned" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Forget what was learned?" });
    await user.click(within(confirm).getByRole("button", { name: "Forget" }));
    expect(await screen.findByText("Nothing learned since.")).toBeInTheDocument();
    expect(db.voices.mathis).toMatchObject({ enrolled: true, learned: 0 });
  });

  it("forgets a voice after a confirmation", async () => {
    const user = userEvent.setup();
    renderApp("/people/mathis");
    await user.click(await screen.findByRole("button", { name: "Forget my voice" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Forget your voice?" });
    expect(confirm).toHaveTextContent("Richie will no longer recognise Mathis on satellites.");
    await user.click(within(confirm).getByRole("button", { name: "Forget" }));
    expect(await screen.findByText("Not recorded yet.")).toBeInTheDocument();
    expect(db.voices.mathis).toBeUndefined();
  });
});

describe("recording a voice", () => {
  it("asks for consent, tries the microphone, takes five phrases, then lets the voice be tried", async () => {
    const { user, dialog } = await openRecording("jules", /^Record their voice/);
    expect(within(dialog).getByRole("heading", { name: "Record Jules's voice" })).toBeInTheDocument();
    expect(dialog).toHaveTextContent("I keep a voiceprint of Jules's voice, never the sound.");
    expect(dialog).toHaveTextContent("Jules reads the phrases, and has to agree.");
    await user.click(within(dialog).getByRole("switch", { name: "Learn over time" }));
    expect(microphone.open).toBe(0); // nothing is heard before consent
    await user.click(within(dialog).getByRole("button", { name: "Start" }));

    expect(await within(dialog).findByRole("heading", { name: "Say hello" })).toHaveFocus();
    await within(dialog).findByText("Say “Hello Richie” to try the microphone.");
    expect(within(dialog).getByRole("button", { name: "Continue" })).toBeDisabled();
    await speak();
    await within(dialog).findByText("I can hear you well.");
    await user.click(within(dialog).getByRole("button", { name: "Continue" }));

    const progress = await within(dialog).findByRole("progressbar", { name: "Phrases kept" });
    await within(dialog).findByText("“Nestor, turn on the lights in the living room.”");
    expect(within(dialog).getByText("Phrase 1 of 5")).toBeInTheDocument();
    await speak();
    await within(dialog).findByText("“What will the weather be like tomorrow morning?”");
    expect(progress).toHaveAttribute("value", "1");
    await speak(); // the mock refuses the second phrase once
    expect(await within(dialog).findByText("That was a bit short. Once more?")).toBeInTheDocument();
    expect(within(dialog).getByText("Phrase 2 of 5")).toBeInTheDocument();
    for (const next of [
      "“Remind me to call the plumber on Thursday.”",
      "“Add bread, apples and coffee to the shopping list.”",
      "“Tell me the story of a lighthouse keeper.”",
    ]) {
      await speak();
      await within(dialog).findByText(next);
    }
    await speak();

    expect(await within(dialog).findByRole("heading", { name: "I recognise Jules's voice" })).toBeInTheDocument();
    expect(db.voices.jules).toMatchObject({ enrolled: true, learning: false });
    expect(dialog).toHaveTextContent("say “Richie, learn to recognise my voice”");
    await user.click(within(dialog).getByRole("button", { name: "Try it" }));
    await within(dialog).findByText("Say something…");
    await speak();
    expect(await within(dialog).findByText("It's Jules.")).toBeInTheDocument();
    expect(within(dialog).getByText("Likeness 82%, recognised from 55%.")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(microphone.open).toBe(0);
    expect(await screen.findByRole("button", { name: "Record again" })).toBeInTheDocument();
  });

  it("says the voice is too quiet before going on", async () => {
    const { user, dialog } = await openRecording("mathis", /^Record again/);
    await user.click(within(dialog).getByRole("button", { name: "Start" }));
    await within(dialog).findByText("Say “Hello Richie” to try the microphone.");
    await speak(0.008);
    expect(await within(dialog).findByText(/I can barely hear you/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Continue" })).toBeDisabled();
  });

  it("lets another microphone be chosen", async () => {
    const { user, dialog } = await openRecording("mathis", /^Record again/);
    await user.click(within(dialog).getByRole("button", { name: "Start" }));
    const choice = await within(dialog).findByRole("combobox", { name: "Microphone" });
    expect(choice).toHaveTextContent("Desk microphone");
    await user.click(choice);
    await user.click(await screen.findByRole("option", { name: "Headset" }));
    await waitFor(() => expect(choice).toHaveTextContent("Headset"));
  });

  it("says what to do when the browser refuses the microphone", async () => {
    microphone.problem = "denied";
    const { user, dialog } = await openRecording("mathis", /^Record again/);
    await user.click(within(dialog).getByRole("button", { name: "Start" }));
    expect(await within(dialog).findByText(/The browser refuses the microphone/)).toBeInTheDocument();
    microphone.problem = null;
    await user.click(within(dialog).getByRole("button", { name: "Try again" }));
    expect(await within(dialog).findByText("Say “Hello Richie” to try the microphone.")).toBeInTheDocument();
  });

  it("abandons the recording when closed midway: nothing is kept", async () => {
    const { user, dialog } = await toPhrases();
    await speak();
    await within(dialog).findByText("“What will the weather be like tomorrow morning?”");
    expect(recordingsInProgress()).toBe(1);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(recordingsInProgress()).toBe(0));
    expect(db.voices.jules).toBeUndefined();
    expect(microphone.open).toBe(0);
  });
});
