import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { liveItem, renderApp } from "@/test/render";

const stories = async () => screen.findAllByRole("article");
/** A story by its text; titles may arrive a moment after the story (a task's or a watch's own answer). */
const storyWith = async (text: string | RegExp) =>
  waitFor(
    async () => {
      const all = await stories();
      const found = all.find((a) =>
        typeof text === "string" ? a.textContent?.includes(text) : text.test(a.textContent ?? ""),
      );
      if (!found) throw new Error(`no story with ${text}`);
      return found;
    },
    { timeout: 4_000 },
  );

describe("the journal", () => {
  it("tells a watch as one chain, from the trigger to the message, with the reason", async () => {
    renderApp("/journal");
    const chain = await storyWith("Messages from Jules's school.");
    for (const step of ["triggered", "decision", "not delivered", "written"]) {
      expect(within(chain).getByText(step)).toBeInTheDocument();
    }
    expect(chain).toHaveTextContent("why: Mathis is in the office");
  });

  it("reads a conversation as a transcript, what happened in between folded into one line", async () => {
    const user = userEvent.setup();
    renderApp("/journal");
    const thread = await storyWith("turn off the kitchen light");
    expect(within(thread).getByText("Richie, turn off the kitchen light.")).toBeInTheDocument();
    expect(within(thread).getByText("It's off.")).toBeInTheDocument();
    const between = within(thread).getByRole("button", { name: /What happened: 1 tool · .*fallback answer/ });
    expect(within(thread).queryByRole("button", { name: "Tool ha_turn_off: details" })).not.toBeInTheDocument();
    await user.click(between);
    expect(within(thread).getByRole("button", { name: "Tool ha_turn_off: details" })).toBeVisible();
    expect(within(thread).getByText(/light\.kitchen: off/)).toBeVisible();
    expect(thread).toHaveTextContent("Fallback answer: model too slow");
  });

  it("joins live events to their conversation at the top", async () => {
    const { stream } = renderApp("/journal");
    await stories();
    stream.emit(liveItem({ detail: "Richie, what time is it?", links: { session: "s-new", turn: "u-new" } }));
    stream.emit(
      liveItem({
        type: "conversation.turn.assistant",
        message: { id: "journal-assistant-answered", args: { assistant: "Richie" } },
        text: "Richie answered",
        detail: "It's 4 pm.",
        people: [],
        links: { session: "s-new", turn: "u-new" },
      }),
    );
    const [first] = await stories();
    expect(first).toHaveTextContent("what time is it");
    expect(first).toHaveTextContent("It's 4 pm.");
  });

  it("ignores live events the filters exclude", async () => {
    const { stream } = renderApp(`/journal?kinds=${encodeURIComponent(JSON.stringify(["tool"]))}`);
    await stories();
    stream.emit(liveItem({ kind: "conversation", detail: "Filtered out", links: { session: "s-x" } }));
    expect(screen.queryByText(/Filtered out/)).not.toBeInTheDocument();
  });

  it("holds new events while paused, and shows them on request", async () => {
    const user = userEvent.setup();
    const { stream } = renderApp("/journal");
    await stories();
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByText("paused")).toBeInTheDocument();
    stream.emit(liveItem({ detail: "Waiting 1", links: { session: "s-a" } }));
    stream.emit(liveItem({ detail: "Waiting 2", links: { session: "s-b" } }));
    expect(screen.queryByText(/Waiting 1/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "2 new events" }));
    expect(await screen.findByText(/Waiting 1/)).toBeInTheDocument();
  });

  it("filters by a facet from its searchable list, by keyboard, with counts", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/journal");
    await stories();
    await user.click(screen.getByRole("button", { name: /^Person/ }));
    const search = await screen.findByPlaceholderText("Filter Person…");
    expect(screen.getByRole("option", { name: /Léa/ })).toHaveTextContent(/\d+/);
    await user.type(search, "lé");
    expect(screen.queryByRole("option", { name: /Mathis/ })).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(router.state.location.search).toEqual({ person: "lea" }));
    await waitFor(async () => {
      for (const story of await stories()) expect(story).toHaveTextContent("Léa");
    });
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(router.state.location.search).toEqual({}));
  });

  it("opens an event in the drawer from the keyboard, with its raw record, and closes it with Escape", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/journal");
    await stories();
    await user.keyboard("j");
    expect(document.activeElement).toHaveAttribute("data-journal-entry");
    await user.keyboard("{Enter}");
    const sheet = await screen.findByRole("dialog");
    expect(await within(sheet).findByRole("heading", { name: "JSON" })).toBeInTheDocument();
    expect(router.state.location.search).toHaveProperty("event");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(router.state.location.search).not.toHaveProperty("event");
  });

  it("focuses the search with /, and says when nothing matches", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/journal");
    await stories();
    await user.keyboard("/");
    expect(screen.getByRole("searchbox", { name: "Search the journal" })).toHaveFocus();
    await user.keyboard("grapefruit{Enter}");
    await waitFor(() => expect(router.state.location.search).toEqual({ q: "grapefruit" }));
    expect(await screen.findByText("No events for these filters.")).toBeInTheDocument();
  });

  it("loads older events on request", async () => {
    const user = userEvent.setup();
    renderApp("/journal");
    const before = (await stories()).length;
    await user.click(screen.getByRole("button", { name: "Older" }));
    await waitFor(async () => expect((await stories()).length).toBeGreaterThan(before));
  });

  it("shows whether the agent is online beside its name", async () => {
    const { stream } = renderApp("/journal");
    await stories();
    expect(screen.getByRole("link", { name: "Richie, online" })).toBeInTheDocument();
    stream.status("closed");
    expect(await screen.findByRole("link", { name: "Richie, offline" })).toBeInTheDocument();
  });
});
