import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { liveItem, renderApp } from "@/test/render";

const part = (name: string | RegExp) => screen.findByRole("region", { name });

describe("today: the household as one picture, then what it asks, does and plans", () => {
  it("greets, shows who is where, the work under way and what comes next", async () => {
    renderApp("/");
    expect(
      await screen.findByRole("heading", { level: 1, name: /Good evening|Good morning|Good night|Hello/ }),
    ).toBeInTheDocument();
    // a room where someone is names them; who is out is said apart
    expect(await screen.findByRole("button", { name: "Living room · Mathis, Jules" })).toBeInTheDocument();
    expect(screen.getByText("Out").parentElement).toHaveTextContent("Léa");
    // full titles, never cut
    expect(
      await within(await part(/^Right now/)).findByText("Prepare the health insurance claim for Jules's glasses."),
    ).toBeInTheDocument();
    expect(
      within(await part("Coming up")).getByText(/Quiet hours from 22:30 to 07:30|Silence until 07:30/),
    ).toBeInTheDocument();
    expect((await part(/^What I need from you/)).querySelectorAll("li").length).toBeGreaterThan(0);
  });

  it("opens a room in place: who is there, its devices and what one may do through them", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Living room · Mathis, Jules" }));
    const room = await screen.findByRole("dialog", { name: "Living room" });
    expect(within(room).getByText("Mathis, Jules are here.")).toBeInTheDocument();
    expect(within(room).getByRole("link", { name: /Mathis/ })).toHaveAttribute("href", "/people/mathis");
    expect(await within(room).findByRole("button", { name: /^View / })).toBeInTheDocument();
    expect(within(room).getByRole("link", { name: /The whole journal/ })).toHaveAttribute(
      "href",
      "/journal?room=living+room",
    );
  });

  it("takes in what arrives live: the agent listens, the day gets a new moment", async () => {
    const { stream } = renderApp("/");
    const day = await screen.findByRole("list", { name: "Since this morning" });
    await waitFor(() => expect(within(day).getAllByRole("listitem").length).toBeGreaterThan(0));
    stream.emit(
      liveItem({ id: "live-1", room: "kitchen", links: { session: "s-live" }, people: [{ id: "lea", name: "Léa" }] }),
    );
    expect(await screen.findByText(/I'm listening to Léa \(kitchen\)/)).toBeInTheDocument();
    await waitFor(() => expect(within(day).getAllByRole("link")[0]).toHaveAttribute("href", "/journal?session=s-live"));
    expect(within(day).getAllByRole("link")[0]).toHaveTextContent("Conversation with Léa (1 turn)");
  });

  it("is calm when nothing needs a person: the agent available, nothing asked of you", async () => {
    for (const c of db.connections) c.status = "connected";
    db.pairing = [];
    for (const s of db.satellites) s.connected = true;
    for (const t of db.tasks) if (t.status === "running" || t.status === "failed") t.status = "completed";
    db.journal = db.journal.filter((e) => !e.item.type.endsWith("delivery_failed"));
    for (const c of db.system.components) c.health = "started";
    (db.config.document.initiative as Record<string, unknown>).quiet_hours = null;
    renderApp("/");
    expect(await screen.findByText("All quiet.")).toBeInTheDocument();
    expect(screen.getByText(/Richie · available/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: /What I need from you/ })).not.toBeInTheDocument(),
    );
  });

  it("shows what the agent says it is doing, as the stream tells it", async () => {
    const { stream } = renderApp("/");
    expect(await screen.findByText(/Richie · working/)).toBeInTheDocument();
    stream.activity({
      state: "listening",
      since: new Date().toISOString(),
      replies: 1,
      tasks: 2,
      listening_rooms: ["living room"],
      quiet: false,
    });
    expect(await screen.findByText(/Richie · listening/)).toBeInTheDocument();
  });

  it("says when it will write, from the agent's initiative", async () => {
    renderApp("/");
    expect(await within(await part("Coming up")).findByText("Follow-up to Mathis on telegram")).toBeInTheDocument();
  });
});
