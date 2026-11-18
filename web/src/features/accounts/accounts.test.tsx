import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("accounts", () => {
  it("shows who has access, each with their role and what it allows", async () => {
    renderApp("/accounts");
    const people = await screen.findByRole("region", { name: /^Who has access/ });
    const lea = await within(people).findByRole("link", { name: /Léa/ });
    expect(lea).toHaveAttribute("href", "/accounts/acc-lea");
    expect(lea).toHaveTextContent("administrator");
    expect(lea).toHaveTextContent("Connections, satellites and supervision, without accounts.");
    expect(within(people).getByRole("link", { name: /Mathis/ })).toHaveTextContent("you");
  });

  it("protects the last active owner and says why", async () => {
    renderApp("/accounts/acc-mathis");
    expect(await screen.findByRole("combobox", { name: "Role" })).toHaveAttribute("data-disabled");
    expect(screen.getByRole("button", { name: "Disable…" })).toBeDisabled();
    expect(screen.getAllByText("At least one active owner is required.").length).toBeGreaterThan(0);
  });

  it("changes a role from the keyboard", async () => {
    const user = userEvent.setup();
    renderApp("/accounts/acc-lea");
    const role = await screen.findByRole("combobox", { name: "Role" });
    role.focus();
    await user.keyboard("{Enter}");
    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByRole("option", { name: "administrator" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowUp}{Enter}");
    expect(await screen.findByText("Léa is now member.")).toBeInTheDocument();
    expect(db.accounts.find((a) => a.id === "acc-lea")?.role).toBe("member");
    expect(await screen.findByText("Their own journal, connections and memories.")).toBeInTheDocument();
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
    expect(await screen.findByRole("alert")).toHaveTextContent("The household must keep at least one owner");
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

  // focus, Escape and focus back on this dialog are checked in a real browser (e2e/open-states.spec.ts)
  it("invites from a dialog and hands over the link", async () => {
    const user = userEvent.setup();
    renderApp("/accounts");
    await user.click(await screen.findByRole("button", { name: "Invite…" }));
    const dialog = await screen.findByRole("dialog", { name: "Invite someone" });
    const person = within(dialog).getByRole("combobox", { name: "Household member" });
    await user.clear(person);
    await user.type(person, "jul");
    await user.keyboard("{Enter}");
    await user.click(within(dialog).getByRole("button", { name: "Create the invitation" }));
    expect(await within(dialog).findByText(/Send this link to/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Copy the invitation link" })).toBeInTheDocument();
    expect(db.invitations.some((i) => i.status === "pending" && i.person?.id === "jules")).toBe(true);
    // once the dialog is left, the invitation waits on the page, where one invites
    await user.click(within(dialog).getByRole("button", { name: "Done" }));
    const waiting = await screen.findByRole("region", { name: /^Pending invitations/ });
    expect(await within(waiting).findByText("Jules")).toBeInTheDocument();
  });

  it("withdraws a pending invitation only once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/accounts");
    const waiting = await screen.findByRole("region", { name: /^Pending invitations/ });
    expect(await within(waiting).findByText("Odile")).toBeInTheDocument();
    await user.click(within(waiting).getByRole("button", { name: "Withdraw…" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Withdraw this invitation?" });
    expect(within(confirm).getByText("The link made for Odile stops working.")).toBeInTheDocument();
    expect(db.invitations.find((i) => i.id === "inv-odile")?.status).toBe("pending");
    await user.click(within(confirm).getByRole("button", { name: "Withdraw" }));
    expect(await within(waiting).findByText("No pending invitation.")).toBeInTheDocument();
  });
});
