import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("a connection's pages", () => {
  it("explains why an account needs reconnecting and opens the connect sheet in place", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/connections/c-gmail-mathis");
    expect(await screen.findByText(/ne peut plus utiliser ce compte/)).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Reconnecter…" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/connections/catalogue"));
    expect(router.state.location.search).toEqual({ connect: "google", replaces: "c-gmail-mathis" });
    const sheet = await screen.findByRole("dialog", { name: "Gmail" });
    expect(
      within(sheet).getByText(/l'ancien accès reste actif jusqu'à ce que le nouveau fonctionne/),
    ).toBeInTheDocument();
  });

  it("moves between its tabs with the URL", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/connections/c-mcp-ha");
    const tabs = await screen.findByRole("tablist", { name: "Sections de la connexion" });
    await user.click(within(tabs).getByRole("tab", { name: /Outils/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/connections/c-mcp-ha/tools"));
    expect(within(tabs).getByRole("tab", { name: /Outils/ })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("switch", { name: /ha_unlock/ })).not.toBeChecked();
  });

  it("saves tool switches and the write confirmation", async () => {
    const user = userEvent.setup();
    renderApp("/connections/c-imap-lea/tools");
    const save = await screen.findByRole("button", { name: "Enregistrer" });
    expect(save).toBeDisabled();
    await user.click(screen.getByRole("switch", { name: /mail_send/ }));
    await user.click(screen.getByRole("checkbox", { name: /Demander confirmation avant d'écrire/ }));
    expect(screen.getByText("● modifications non enregistrées")).toBeInTheDocument();
    await user.click(save);
    expect(await screen.findByText("Réglages des outils enregistrés.")).toBeInTheDocument();
    expect(db.connections.find((c) => c.id === "c-imap-lea")?.confirm_writes).toBe(false);
    expect(db.tools["c-imap-lea"]?.find((t) => t.name === "mail_send")?.enabled).toBe(true);
  });

  it("disconnects only once confirmed; Escape cancels", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/connections/c-imap-lea/settings");
    await user.click(await screen.findByRole("button", { name: "Déconnecter…" }));
    await screen.findByRole("alertdialog", { name: "Déconnecter lea@lambert.family ?" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(db.connections.some((c) => c.id === "c-imap-lea")).toBe(true);

    await user.click(screen.getByRole("button", { name: "Déconnecter…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Déconnecter" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/connections"));
    expect(db.connections.some((c) => c.id === "c-imap-lea")).toBe(false);
    expect(await screen.findByText(/déconnecté : ses accès ont été révoqués et oubliés/)).toBeInTheDocument();
  });

  it("greets the account the provider brought back", async () => {
    const { router } = renderApp("/connections/c-mcp-ha?connected=1");
    expect(await screen.findByText("Compte Home Assistant · maison connecté.")).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toEqual({}));
  });

  it("explains a refused consent", async () => {
    renderApp("/connections/failed?kind=google&error=access_denied");
    expect(await screen.findByRole("heading", { name: "Autorisation refusée" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Recommencer" })).toHaveAttribute(
      "href",
      "/connections/catalogue?connect=google",
    );
  });

  it("says so when the connection is gone", async () => {
    renderApp("/connections/c-nope");
    expect(await screen.findByRole("alert")).toHaveTextContent("Connexion introuvable.");
  });
});
