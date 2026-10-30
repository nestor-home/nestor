import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("signing in", () => {
  it("refuses a wrong password, then lands where the person was going", async () => {
    db.signedIn = null;
    const user = userEvent.setup();
    const { router } = renderApp("/login?next=%2Fwatches");
    await user.type(await screen.findByLabelText("Identifiant"), "lea");
    await user.type(screen.getByLabelText("Mot de passe"), "mauvais");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Adresse ou mot de passe incorrect.");

    await user.clear(screen.getByLabelText("Mot de passe"));
    await user.type(screen.getByLabelText("Mot de passe"), "nestor");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/watches"));
  });

  it("never follows a `next` to another site", async () => {
    db.signedIn = null;
    const user = userEvent.setup();
    const { router } = renderApp("/login?next=%2F%2Fevil.example");
    await user.type(await screen.findByLabelText("Identifiant"), "mathis");
    await user.type(screen.getByLabelText("Mot de passe"), "nestor");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/journal"));
  });
});

describe("accepting an invitation", () => {
  it("checks the password before creating the account", async () => {
    db.signedIn = null;
    const user = userEvent.setup();
    const { router } = renderApp("/invitation/inv-odile");
    expect(await screen.findByText(/comme/)).toHaveTextContent("membre, pour Odile");
    expect(screen.getByLabelText("Identifiant")).toHaveValue("odile");
    await user.type(screen.getByLabelText("Mot de passe"), "court");
    await user.type(screen.getByLabelText("Confirmez le mot de passe"), "court");
    await user.click(screen.getByRole("button", { name: "Accepter l'invitation" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Au moins 12 caractères.");

    await user.clear(screen.getByLabelText("Mot de passe"));
    await user.type(screen.getByLabelText("Mot de passe"), "le thé de grand-mère");
    await user.clear(screen.getByLabelText("Confirmez le mot de passe"));
    await user.type(screen.getByLabelText("Confirmez le mot de passe"), "le thé de grand-mere");
    await user.click(screen.getByRole("button", { name: "Accepter l'invitation" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Les deux mots de passe diffèrent.");

    await user.clear(screen.getByLabelText("Confirmez le mot de passe"));
    await user.type(screen.getByLabelText("Confirmez le mot de passe"), "le thé de grand-mère");
    await user.click(screen.getByRole("button", { name: "Accepter l'invitation" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/journal"));
    expect(db.accounts.some((a) => a.login === "odile" && a.role === "member" && a.person === "odile")).toBe(true);
  });

  it("explains a used or unknown link", async () => {
    db.signedIn = null;
    renderApp("/invitation/inv-perime");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Cette invitation n'existe pas, a expiré ou a déjà servi.",
    );
  });
});
