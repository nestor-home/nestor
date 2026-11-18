import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("a person's page", () => {
  it("leads with the person, where they are and how the agent reaches them", async () => {
    renderApp("/people/mathis");
    expect(await screen.findByRole("heading", { name: "Mathis", level: 1 })).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumbs" });
    expect(within(crumbs).getByRole("link", { name: "The house" })).toHaveAttribute("href", "/house");
    expect(screen.getByText(/^at home · /)).toBeInTheDocument();
    expect(screen.getByText("reached first on Telegram")).toBeInTheDocument();
    const reach = await screen.findByRole("region", { name: /^How .* reaches them$/ });
    const telegram = within(reach).getByText("@mathis_l").closest("li") as HTMLElement;
    expect(telegram).toHaveTextContent("Telegram");
    expect(within(telegram).getByText("first")).toBeInTheDocument();
    expect(within(reach).getByRole("link", { name: "Open the account mathis" })).toHaveAttribute(
      "href",
      "/accounts/acc-mathis",
    );
  });

  it("says so when nobody set a channel that comes first", async () => {
    const odile = db.people.find((p) => p.id === "odile");
    if (!odile) throw new Error("Odile is in the mocks");
    odile.reach = null;
    renderApp("/people/odile");
    const reach = await screen.findByRole("region", { name: /^How .* reaches them$/ });
    expect(reach).toHaveTextContent(/No channel comes first: .* answers where it was asked\./);
    expect(within(reach).queryByText("first")).not.toBeInTheDocument();
    expect(reach).toHaveTextContent("no account");
  });

  it("opens what concerns them from its tabs: memories that open in place, connected accounts", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/people/jules");
    await user.click(await screen.findByRole("tab", { name: "Memories" }));
    await user.click(await screen.findByRole("button", { name: /Jules is allergic to peanuts\./ }));
    expect(await screen.findByRole("dialog", { name: "Jules is allergic to peanuts." })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("tab", { name: "Connections" }));
    expect(await screen.findByText("No connected account for Jules.")).toBeInTheDocument();
    // connecting from a person's page starts with that person as the owner
    expect(screen.getByRole("link", { name: "Open the catalogue" })).toHaveAttribute(
      "href",
      "/connections/catalogue?owner=jules",
    );
    expect(router.state.location.pathname).toBe("/people/jules/connections");
  });
});
