import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { liveItem, renderApp } from "@/test/render";

const mind = () => screen.findByRole("region", { name: "Ce que Richie perçoit en ce moment" });

describe("the home: inside the agent's mind", () => {
  it("shows the house as the agent perceives it and what it reaches, each a link", async () => {
    renderApp("/");
    const map = await mind();
    expect(await within(map).findAllByRole("link", { name: /^salon : Mathis, Jules/ })).not.toHaveLength(0);
    expect(within(map).getAllByRole("link", { name: "Hors de la maison : Léa" })[0]).toHaveAttribute("href", "/people");
    expect((await within(map).findAllByRole("link", { name: /^Tâche : Préparer le dossier/ }))[0]).toHaveAttribute(
      "href",
      "/tasks/t-4410aa",
    );
    expect(within(map).getAllByRole("link", { name: /Richie, travaille/ })[0]).toBeInTheDocument();
  });

  it("takes in what arrives live: the agent listens, the day gets a new mark", async () => {
    const { stream } = renderApp("/");
    await mind();
    const day = await screen.findByRole("list", { name: /moments aujourd'hui/ });
    const before = within(day).getAllByRole("listitem").length;
    stream.emit(liveItem({ uid: "live-1", room: "cuisine", links: { session: "s-live" }, people: ["lea"] }));
    expect((await screen.findAllByRole("link", { name: /Richie, à l'écoute/ }))[0]).toBeInTheDocument();
    await waitFor(() => expect(within(day).getAllByRole("listitem")).toHaveLength(before + 1));
    const mark = within(day)
      .getAllByRole("link", { name: /conversation avec Léa/ })
      .find((a) => a.getAttribute("href") === "/journal?session=s-live");
    expect(mark).toBeDefined();
  });

  it("says when to expect silence, from the quiet hours of the file", async () => {
    renderApp("/");
    expect(await screen.findByText(/Heures calmes de 22:30 à 07:30|Silence jusqu'à 07:30/)).toBeInTheDocument();
  });

  it("is calm when nothing needs a person: the agent at rest, no attention band", async () => {
    for (const c of db.connections) c.status = "connected";
    db.pairing = [];
    for (const s of db.satellites) s.connected = true;
    for (const t of db.tasks) if (t.status === "running" || t.status === "failed") t.status = "completed";
    db.journal = db.journal.filter((e) => !e.type.endsWith("delivery_failed"));
    for (const c of db.system.components) c.health = "ok";
    (db.config.document.initiative as Record<string, unknown>).quiet_hours = null; // not asleep either
    renderApp("/");
    const map = await mind();
    await waitFor(() => expect(within(map).getAllByText(/Tout est calme/)[0]).toBeInTheDocument());
    expect(within(map).getAllByText("au repos")[0]).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Ce qui demande votre attention/ })).not.toBeInTheDocument();
  });
});
