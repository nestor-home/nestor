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
    const chain = await storyWith("Les messages de l'école de Jules.");
    for (const step of ["déclenchée", "triée", "décision", "non transmis", "écrit"]) {
      expect(within(chain).getByText(step)).toBeInTheDocument();
    }
    expect(chain).toHaveTextContent("pourquoi Mathis est dans la pièce « bureau »");
  });

  it("threads a conversation with its tool calls, collapsed until asked", async () => {
    const user = userEvent.setup();
    renderApp("/journal");
    const thread = await storyWith("éteins la lumière de la cuisine");
    const call = within(thread).getByRole("button", { name: "Outil ha_turn_off : détails" });
    expect(within(thread).getByText("ok")).toBeInTheDocument();
    expect(within(thread).queryByText(/light\.cuisine : off/)).not.toBeInTheDocument();
    await user.click(call);
    expect(within(thread).getByText(/light\.cuisine : off/)).toBeVisible();
    expect(thread).toHaveTextContent("Réponse de secours : modèle trop lent");
  });

  it("joins live events to their conversation at the top", async () => {
    const { stream } = renderApp("/journal");
    await stories();
    stream.emit(liveItem({ detail: "Richie, quelle heure est-il ?", links: { session: "s-new", turn: "u-new" } }));
    stream.emit(
      liveItem({
        type: "conversation.assistant_turn",
        message: { id: "journal-assistant-answered", args: { assistant: "Richie" } },
        text: "Richie a répondu",
        detail: "Il est 16 h.",
        people: [],
        links: { session: "s-new", turn: "u-new" },
      }),
    );
    const [first] = await stories();
    expect(first).toHaveTextContent("quelle heure est-il");
    expect(first).toHaveTextContent("Il est 16 h.");
  });

  it("ignores live events the filters exclude", async () => {
    const { stream } = renderApp("/journal?kinds=tool");
    await stories();
    stream.emit(liveItem({ kind: "conversation", detail: "Hors filtre", links: { session: "s-x" } }));
    expect(screen.queryByText(/Hors filtre/)).not.toBeInTheDocument();
  });

  it("holds new events while paused, and shows them on request", async () => {
    const user = userEvent.setup();
    const { stream } = renderApp("/journal");
    await stories();
    await user.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByText("en pause")).toBeInTheDocument();
    stream.emit(liveItem({ detail: "En attente 1", links: { session: "s-a" } }));
    stream.emit(liveItem({ detail: "En attente 2", links: { session: "s-b" } }));
    expect(screen.queryByText(/En attente 1/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "2 nouveaux événements" }));
    expect(await screen.findByText(/En attente 1/)).toBeInTheDocument();
  });

  it("filters by a facet from its searchable list, by keyboard, with counts", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/journal");
    await stories();
    await user.click(screen.getByRole("button", { name: /^Personne/ }));
    const search = await screen.findByPlaceholderText("Filtrer : Personne…");
    expect(screen.getByRole("option", { name: /Léa/ })).toHaveTextContent(/\d+/);
    await user.type(search, "lé");
    expect(screen.queryByRole("option", { name: /Mathis/ })).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(router.state.location.search).toEqual({ person: "lea" }));
    await waitFor(async () => {
      for (const story of await stories()) expect(story).toHaveTextContent("Léa");
    });
    await user.click(screen.getByRole("button", { name: "Effacer les filtres" }));
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
    expect(await within(sheet).findByRole("heading", { name: "Enregistrement brut" })).toBeInTheDocument();
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
    expect(screen.getByRole("searchbox", { name: "Chercher dans le journal" })).toHaveFocus();
    await user.keyboard("pamplemousse{Enter}");
    await waitFor(() => expect(router.state.location.search).toEqual({ q: "pamplemousse" }));
    expect(await screen.findByText("Rien dans le journal pour ces filtres.")).toBeInTheDocument();
  });

  it("loads older events on request", async () => {
    const user = userEvent.setup();
    renderApp("/journal");
    const before = (await stories()).length;
    await user.click(screen.getByRole("button", { name: "Plus ancien" }));
    await waitFor(async () => expect((await stories()).length).toBeGreaterThan(before));
  });

  it("shows whether the agent is online beside its name", async () => {
    const { stream } = renderApp("/journal");
    await stories();
    expect(screen.getByRole("link", { name: "Richie, en ligne" })).toBeInTheDocument();
    stream.status("closed");
    expect(await screen.findByRole("link", { name: "Richie, hors ligne" })).toBeInTheDocument();
  });
});
