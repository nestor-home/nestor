import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderApp } from "@/test/render";

describe("the connected accounts", () => {
  it("puts the accounts to reconnect first, each with why, what to do and the way to do it", async () => {
    renderApp("/connections");
    const broken = await screen.findByRole("region", { name: /To reconnect/ });
    const gmail = within(broken).getByRole("link", { name: "mathis@example.com" }).closest("li");
    if (!gmail) throw new Error("the account is not a card of the list");
    expect(within(gmail).getByText("needs reauthorising")).toBeInTheDocument();
    expect(within(gmail).getByText(/Reconnect the account: its settings are kept/)).toBeInTheDocument();
    expect(within(gmail).getByText("Google refused to renew the token (invalid_grant).")).toBeInTheDocument();
    expect(within(gmail).getByRole("link", { name: "Reconnect…" })).toHaveAttribute(
      "href",
      "/connections/catalogue?connect=google&replaces=c-gmail-mathis",
    );

    const working = screen.getByRole("region", { name: /Connected/ });
    expect(within(working).getByRole("link", { name: /lea@martin\.family/ })).toHaveAttribute(
      "href",
      "/connections/c-imap-lea",
    );
    expect(within(working).queryByText("mathis@example.com")).not.toBeInTheDocument();
  });

  it("narrows the list to what needs someone, or to one person's accounts", async () => {
    const user = userEvent.setup();
    renderApp("/connections");
    await user.click(await screen.findByRole("button", { name: /^To reconnect/ }));
    expect(screen.queryByRole("region", { name: /Connected/ })).not.toBeInTheDocument();
    expect(screen.getByText("lea@192.168.1.20:8808")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Léa/ }));
    expect(screen.getByText("lea@192.168.1.20:8808")).toBeInTheDocument();
    expect(screen.getByText("lea@martin.family")).toBeInTheDocument();
    expect(screen.queryByText("mathis@example.com")).not.toBeInTheDocument();
    expect(screen.queryByText("mathis.martin@outlook.com")).not.toBeInTheDocument();
  });
});

describe("the catalogue", () => {
  it("says which service still lacks its OAuth client", async () => {
    renderApp("/connections/catalogue");
    const accounts = await screen.findByRole("region", { name: "Mail, calendars and files" });
    expect(within(accounts).getByRole("button", { name: /Microsoft/ })).toHaveTextContent("OAuth client missing");
    expect(within(accounts).getByRole("button", { name: /Google/ })).not.toHaveTextContent("OAuth client missing");
  });

  it("opens the connect sheet on a known server, its address already filled", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/connections/catalogue");
    const servers = await screen.findByRole("region", { name: "Tool servers" });
    await user.click(within(servers).getByRole("button", { name: "Linear" }));
    await waitFor(() => expect(router.state.location.search).toEqual({ connect: "mcp", preset: "Linear" }));
    const sheet = await screen.findByRole("dialog");
    expect(await within(sheet).findByLabelText("Server address")).toHaveValue("https://mcp.linear.app/mcp");
    expect(within(sheet).getByRole("button", { name: "Linear" })).toHaveAttribute("aria-pressed", "true");
  });
});
