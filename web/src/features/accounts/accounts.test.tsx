import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("accounts", () => {
  it("protects the last active owner and says why", async () => {
    renderApp("/accounts");
    expect(await screen.findByRole("combobox", { name: "Role of Mathis" })).toHaveAttribute("data-disabled");
    expect(screen.getByText("At least one active owner is required.")).toBeInTheDocument();
  });

  it("changes a role from the keyboard", async () => {
    const user = userEvent.setup();
    renderApp("/accounts");
    const role = await screen.findByRole("combobox", { name: "Role of Léa" });
    role.focus();
    await user.keyboard("{Enter}");
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "administrator" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowUp}{Enter}");
    expect(await screen.findByText("Léa is now member.")).toBeInTheDocument();
    expect(db.accounts.find((a) => a.id === "acc-lea")?.role).toBe("member");
  });

  it("shows the server's refusal when the rule was not visible", async () => {
    const user = userEvent.setup();
    const lea = db.accounts.find((a) => a.id === "acc-lea");
    if (lea) lea.role = "owner";
    renderApp("/accounts/acc-mathis");
    const role = await screen.findByRole("combobox", { name: "Role" });
    // between the page loading and the change, Léa lost her owner role elsewhere
    if (lea) lea.role = "admin";
    await user.click(role);
    await user.click(await screen.findByRole("option", { name: "member" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The household must keep at least one active owner.");
  });

  it("disables an account only once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/accounts/acc-lea");
    await user.click(await screen.findByRole("button", { name: "Disable…" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Disable Léa's account?" });
    await user.click(within(dialog).getByRole("button", { name: "Disable" }));
    await waitFor(() => expect(db.accounts.find((a) => a.id === "acc-lea")?.disabled).toBe(true));
    expect(await screen.findByText("Léa's account disabled.")).toBeInTheDocument();
  });

  it("invites from a dialog that takes focus, closes on Escape and hands over the link", async () => {
    const user = userEvent.setup();
    renderApp("/accounts");
    const open = await screen.findByRole("button", { name: "Invite…" });
    await user.click(open);
    let dialog = await screen.findByRole("dialog", { name: "Invite someone" });
    // focus goes into the dialog; cycling through the focus guards is checked in a real browser
    // (e2e/open-states.spec.ts), jsdom does not run them
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(open).toHaveFocus();

    await user.click(open);
    dialog = await screen.findByRole("dialog", { name: "Invite someone" });
    const person = within(dialog).getByRole("combobox", { name: "Household member" });
    await user.clear(person);
    await user.type(person, "jul");
    await user.keyboard("{Enter}");
    await user.click(within(dialog).getByRole("button", { name: "Create the invitation" }));
    expect(await within(dialog).findByText(/Send this link to/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Copy the invitation link" })).toBeInTheDocument();
    expect(db.invitations.some((i) => i.status === "pending" && i.person === "jules")).toBe(true);
  });
});
