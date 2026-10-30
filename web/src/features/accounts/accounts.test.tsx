import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("accounts", () => {
  it("protects the last active owner and says why", async () => {
    renderApp("/accounts");
    expect(await screen.findByRole("combobox", { name: "Rôle de Mathis" })).toHaveAttribute("data-disabled");
    expect(screen.getByText("Dernier propriétaire actif : le foyer doit en garder au moins un.")).toBeInTheDocument();
  });

  it("changes a role from the keyboard", async () => {
    const user = userEvent.setup();
    renderApp("/accounts");
    const role = await screen.findByRole("combobox", { name: "Rôle de Léa" });
    role.focus();
    await user.keyboard("{Enter}");
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "administrateur" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowUp}{Enter}");
    expect(await screen.findByText("Léa est maintenant membre.")).toBeInTheDocument();
    expect(db.accounts.find((a) => a.id === "acc-lea")?.role).toBe("member");
  });

  it("shows the server's refusal when the rule was not visible", async () => {
    const user = userEvent.setup();
    const lea = db.accounts.find((a) => a.id === "acc-lea");
    if (lea) lea.role = "owner";
    renderApp("/accounts/acc-mathis");
    const role = await screen.findByRole("combobox", { name: "Rôle" });
    // between the page loading and the change, Léa lost her owner role elsewhere
    if (lea) lea.role = "admin";
    await user.click(role);
    await user.click(await screen.findByRole("option", { name: "membre" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le foyer doit garder au moins un propriétaire actif.");
  });

  it("disables an account only once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/accounts/acc-lea");
    await user.click(await screen.findByRole("button", { name: "Désactiver…" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Désactiver le compte de Léa ?" });
    await user.click(within(dialog).getByRole("button", { name: "Désactiver" }));
    await waitFor(() => expect(db.accounts.find((a) => a.id === "acc-lea")?.disabled).toBe(true));
    expect(await screen.findByText("Compte de Léa désactivé.")).toBeInTheDocument();
  });

  it("invites from a dialog that takes focus, closes on Escape and hands over the link", async () => {
    const user = userEvent.setup();
    renderApp("/accounts");
    const open = await screen.findByRole("button", { name: "Inviter…" });
    await user.click(open);
    let dialog = await screen.findByRole("dialog", { name: "Inviter quelqu'un" });
    // focus goes into the dialog; cycling through the focus guards is checked in a real browser
    // (e2e/open-states.spec.ts), jsdom does not run them
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(open).toHaveFocus();

    await user.click(open);
    dialog = await screen.findByRole("dialog", { name: "Inviter quelqu'un" });
    const person = within(dialog).getByRole("combobox", { name: "Personne du foyer" });
    await user.clear(person);
    await user.type(person, "jul");
    await user.keyboard("{Enter}");
    await user.click(within(dialog).getByRole("button", { name: "Créer l'invitation" }));
    expect(await within(dialog).findByText(/Envoyez ce lien à/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Copier le lien d'invitation" })).toBeInTheDocument();
    expect(db.invitations.some((i) => i.status === "pending" && i.person === "jules")).toBe(true);
  });
});
