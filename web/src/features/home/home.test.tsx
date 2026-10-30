import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { liveItem, renderApp } from "@/test/render";

const band = (name: string | RegExp) => screen.findByRole("region", { name });

describe("the home: the agent first, then the house, the work, the day", () => {
  it("says what the agent attends to, and lists the house, the work and what comes next in full", async () => {
    renderApp("/");
    expect(await screen.findByRole("heading", { level: 1, name: /Bonsoir|Bonjour|Bonne nuit/ })).toBeInTheDocument();
    const house = await band("La maison");
    expect(within(house).getByRole("link", { name: /Salon\s*Mathis, Jules/ })).toHaveAttribute(
      "href",
      "/journal?room=salon",
    );
    expect(within(house).getByRole("link", { name: /Dehors\s*Léa/ })).toHaveAttribute("href", "/people");
    const now = await band("En ce moment");
    // full titles, never cut
    expect(
      await within(now).findByText("Préparer le dossier de remboursement de la mutuelle pour les lunettes de Jules."),
    ).toBeInTheDocument();
    expect(
      within(await band("À venir")).getByText(/Heures calmes de 22:30 à 07:30|Silence jusqu'à 07:30/),
    ).toBeInTheDocument();
    expect((await band(/^Ce que j'attends de vous/)).querySelectorAll("li").length).toBeGreaterThan(0);
  });

  it("takes in what arrives live: the agent listens, today gets a new moment", async () => {
    const { stream } = renderApp("/");
    const today = await screen.findByRole("list", { name: "Aujourd'hui" });
    await waitFor(() => expect(within(today).getAllByRole("listitem").length).toBeGreaterThan(0));
    stream.emit(liveItem({ uid: "live-1", room: "cuisine", links: { session: "s-live" }, people: ["lea"] }));
    expect(await screen.findByText(/J'écoute Léa \(cuisine\)/)).toBeInTheDocument();
    await waitFor(() =>
      expect(within(today).getAllByRole("link")[0]).toHaveAttribute("href", "/journal?session=s-live"),
    );
    expect(within(today).getAllByRole("link")[0]).toHaveTextContent("Conversation avec Léa (1 tour)");
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
    expect(await screen.findByText("Tout est calme. Je suis là si besoin.")).toBeInTheDocument();
    expect(screen.getByText(/Richie · disponible/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: /Ce que j'attends de vous/ })).not.toBeInTheDocument(),
    );
  });

  it("shows what the agent says it is doing, as the stream tells it", async () => {
    const { stream } = renderApp("/");
    expect(await screen.findByText(/Richie · travaille/)).toBeInTheDocument();
    stream.activity({
      state: "listening",
      since: new Date().toISOString(),
      replies: 1,
      tasks: 2,
      listening_rooms: ["salon"],
      quiet: false,
    });
    expect(await screen.findByText(/Richie · à l'écoute/)).toBeInTheDocument();
  });

  it("says when it will write, from the agent's initiative", async () => {
    renderApp("/");
    const next = await band("À venir");
    expect(await within(next).findByText(/Je l'écrirai à Mathis sur telegram à \d\d:\d\d\./)).toBeInTheDocument();
  });
});
