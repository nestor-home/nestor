import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { liveItem, renderApp } from "@/test/render";

const band = (name: string | RegExp) => screen.findByRole("region", { name });

describe("the home: the agent first, then the house, the work, the day", () => {
  it("says what the agent attends to, and lists the house, the work and what comes next in full", async () => {
    renderApp("/");
    expect(
      await screen.findByRole("heading", { level: 1, name: /Good evening|Good morning|Good night|Hello/ }),
    ).toBeInTheDocument();
    const house = await band("The house");
    expect(within(house).getByRole("link", { name: /Living room\s*Mathis, Jules/ })).toHaveAttribute(
      "href",
      "/journal?room=living+room",
    );
    expect(within(house).getByRole("link", { name: /Out\s*Léa/ })).toHaveAttribute("href", "/people");
    const now = await band("Right now");
    // full titles, never cut
    expect(await within(now).findByText("Prepare the health insurance claim for Jules's glasses.")).toBeInTheDocument();
    expect(
      within(await band("Coming up")).getByText(/Quiet hours from 22:30 to 07:30|Silence until 07:30/),
    ).toBeInTheDocument();
    expect((await band(/^What I need from you/)).querySelectorAll("li").length).toBeGreaterThan(0);
  });

  it("takes in what arrives live: the agent listens, today gets a new moment", async () => {
    const { stream } = renderApp("/");
    const today = await screen.findByRole("list", { name: "Today" });
    await waitFor(() => expect(within(today).getAllByRole("listitem").length).toBeGreaterThan(0));
    stream.emit(liveItem({ uid: "live-1", room: "kitchen", links: { session: "s-live" }, people: ["lea"] }));
    expect(await screen.findByText(/I'm listening to Léa \(kitchen\)/)).toBeInTheDocument();
    await waitFor(() =>
      expect(within(today).getAllByRole("link")[0]).toHaveAttribute("href", "/journal?session=s-live"),
    );
    expect(within(today).getAllByRole("link")[0]).toHaveTextContent("Conversation with Léa (1 turn)");
  });

  it("is calm when nothing needs a person: the agent available, nothing asked of you", async () => {
    for (const c of db.connections) c.status = "connected";
    db.pairing = [];
    for (const s of db.satellites) s.connected = true;
    for (const t of db.tasks) if (t.status === "running" || t.status === "failed") t.status = "completed";
    db.journal = db.journal.filter((e) => !e.type.endsWith("delivery_failed"));
    for (const c of db.system.components) c.health = "ok";
    (db.config.document.initiative as Record<string, unknown>).quiet_hours = null;
    renderApp("/");
    expect(await screen.findByText("All is calm. I'm here if you need me.")).toBeInTheDocument();
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
    const next = await band("Coming up");
    expect(await within(next).findByText(/I'll write it to Mathis on telegram at \d\d:\d\d\./)).toBeInTheDocument();
  });
});
