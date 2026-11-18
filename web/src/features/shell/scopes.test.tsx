import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Role } from "@/api";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

function signInAs(role: Role) {
  const account = db.accounts.find((a) => a.id === "acc-lea");
  if (!account) throw new Error("fixture changed");
  account.role = role;
  db.signedIn = account.id;
}

const SPACES = ["Today", "Talk", "Ongoing", "The house", "Settings"];

/** The spaces the navigation offers, by accessible name. */
async function spaces() {
  const nav = await screen.findByRole("navigation", { name: "Sections" });
  return SPACES.filter((name) => within(nav).queryByRole("link", { name: new RegExp(`^${name}`) }));
}

/** What Settings holds for this account, by the title of each card. */
async function settings() {
  await screen.findByRole("heading", { level: 1, name: "Settings" });
  return ["Connections", "Satellites", "Accounts", "Configuration", "System"].filter((name) =>
    screen.queryByRole("link", { name: new RegExp(`^${name}`) }),
  );
}

describe("what the scopes allow", () => {
  it("shows every space to an owner, and everything the installation is made of", async () => {
    renderApp("/settings");
    expect(await spaces()).toEqual(SPACES);
    expect(await settings()).toEqual(["Connections", "Satellites", "Accounts", "Configuration", "System"]);
  });

  it("says where one is: a page reached from a space keeps that space current", async () => {
    renderApp("/journal");
    const nav = await screen.findByRole("navigation", { name: "Sections" });
    expect(within(nav).getByRole("link", { name: /^Today/ })).toHaveAttribute("aria-current", "page");
  });

  it("hides accounts from a guest, and explains it on a direct visit", async () => {
    signInAs("guest");
    renderApp("/accounts");
    expect(await screen.findByRole("heading", { name: "Restricted section" })).toBeInTheDocument();
  });

  it("gives a member the household and their own connections, not the installation", async () => {
    signInAs("member");
    renderApp("/settings");
    expect(await spaces()).toEqual(SPACES);
    expect(await settings()).toEqual(["Connections"]);
  });

  it("hides pairing from whoever may only look at satellites", async () => {
    signInAs("member");
    renderApp("/satellites");
    expect(await screen.findByRole("heading", { name: "Restricted section" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve…" })).not.toBeInTheDocument();
  });

  it("sends a signed-out visitor to the login page, remembering where they were going", async () => {
    db.signedIn = null;
    const { router } = renderApp("/activity");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ next: "/activity" });
  });
});
