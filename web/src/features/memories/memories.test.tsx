import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("memories", () => {
  it("corrects a memory in a dialog, and links to where it was learnt", async () => {
    const user = userEvent.setup();
    renderApp("/memories?about=jules");
    const card = (await screen.findByText("Jules a entraînement de handball le mercredi à 15 h.")).closest(
      "li",
    ) as HTMLElement;
    expect(within(card).getByRole("link", { name: /où il l'a appris/ })).toHaveAttribute(
      "href",
      expect.stringContaining("session=s-jules"),
    );
    const allergy = (await screen.findByText("Jules est allergique aux arachides.")).closest("li") as HTMLElement;
    await user.click(within(allergy).getByRole("button", { name: "Corriger…" }));
    const dialog = await screen.findByRole("dialog", { name: "Corriger le souvenir" });
    const text = within(dialog).getByLabelText("Texte du souvenir");
    await user.clear(text);
    await user.type(text, "Jules est allergique aux arachides et aux noix de cajou.");
    await user.keyboard("{Meta>}{Enter}{/Meta}");
    expect(await screen.findByText("C'est corrigé.")).toBeInTheDocument();
    expect(db.memories.find((m) => m.id === "m-01")?.text).toContain("noix de cajou");
  });

  it("forgets a memory only once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/memories");
    const card = (await screen.findByText(/Odile vient déjeuner/)).closest("li") as HTMLElement;
    await user.click(within(card).getByRole("button", { name: "Oublier…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Oublier" }));
    await waitFor(() => expect(screen.queryByText(/Odile vient déjeuner/)).not.toBeInTheDocument());
    expect(db.memories.some((m) => m.id === "m-04")).toBe(false);
  });

  it("searches and says when nothing matches", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/memories");
    await user.type(await screen.findByLabelText("Rechercher"), "piscine");
    await user.click(screen.getByRole("button", { name: "Chercher" }));
    expect(await screen.findByText("Aucun souvenir ne correspond.")).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ q: "piscine" });
  });
});
