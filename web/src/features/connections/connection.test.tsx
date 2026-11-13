import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("a connection's pages", () => {
  it("explains why an account needs reconnecting and opens the connect sheet in place", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/connections/c-gmail-mathis");
    expect(await screen.findByText(/can no longer use this account/)).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Reconnect…" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/connections/catalogue"));
    expect(router.state.location.search).toEqual({ connect: "google", replaces: "c-gmail-mathis" });
    const sheet = await screen.findByRole("dialog", { name: "Google" });
    expect(within(sheet).getByText(/The old access stays active until the new one works/)).toBeInTheDocument();
  });

  it("says how a message names each service of the account", async () => {
    renderApp("/connections/c-imap-lea");
    const named = await screen.findByRole("region", { name: "In a message" });
    expect(within(named).getByText("@mail")).toBeInTheDocument();
  });

  it("moves between its tabs with the URL", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/connections/c-mcp-ha");
    const tabs = await screen.findByRole("tablist", { name: "Connection sections" });
    await user.click(within(tabs).getByRole("tab", { name: /Tools/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/connections/c-mcp-ha/tools"));
    expect(within(tabs).getByRole("tab", { name: /Tools/ })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("switch", { name: /ha_unlock/ })).not.toBeChecked();
  });

  it("saves tool switches and the write confirmation", async () => {
    const user = userEvent.setup();
    renderApp("/connections/c-imap-lea/tools");
    const save = await screen.findByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    await user.click(screen.getByRole("switch", { name: /mail_send/ }));
    await user.click(screen.getByRole("checkbox", { name: /Ask for confirmation before writing/ }));
    expect(screen.getByText("● unsaved changes")).toBeInTheDocument();
    await user.click(save);
    expect(await screen.findByText("Tool settings saved.")).toBeInTheDocument();
    expect(db.connections.find((c) => c.id === "c-imap-lea")?.confirm_writes).toBe(false);
    expect(db.tools["c-imap-lea"]?.find((t) => t.name === "mail_send")?.enabled).toBe(true);
  });

  it("disconnects only once confirmed; Escape cancels", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/connections/c-imap-lea/settings");
    await user.click(await screen.findByRole("button", { name: "Disconnect…" }));
    await screen.findByRole("alertdialog", { name: "Disconnect lea@lambert.family?" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(db.connections.some((c) => c.id === "c-imap-lea")).toBe(true);

    await user.click(screen.getByRole("button", { name: "Disconnect…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/connections"));
    expect(db.connections.some((c) => c.id === "c-imap-lea")).toBe(false);
    expect(await screen.findByText(/disconnected/)).toBeInTheDocument();
  });

  it("greets the account the provider brought back", async () => {
    const { router } = renderApp("/connections/c-mcp-ha?connected=1");
    expect(await screen.findByText("Account household@homeassistant.local:8123 connected.")).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.search).toEqual({}));
  });

  it("explains a refused consent", async () => {
    renderApp("/connections/failed?kind=google&error=access_denied");
    expect(await screen.findByRole("heading", { name: "Authorisation refused" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start again" })).toHaveAttribute(
      "href",
      "/connections/catalogue?connect=google",
    );
  });

  it.each([
    ["forbidden", "Connection no longer allowed"],
    ["provider_error", "The service did not authorise it"],
    ["expired", "Authorisation request expired"],
  ])("explains why connecting failed (%s)", async (error, title) => {
    renderApp(`/connections/failed?kind=google&error=${error}`);
    expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
  });

  it("says so when the connection is gone", async () => {
    renderApp("/connections/c-nope");
    expect(await screen.findByRole("alert")).toHaveTextContent("This connection does not exist or was removed.");
  });
});
