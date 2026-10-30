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

const ALL = [
  "Aujourd'hui",
  "Journal",
  "Personnes",
  "Souvenirs",
  "Veilles",
  "Tâches",
  "Connexions",
  "Satellites",
  "Système",
  "Comptes",
];

/** The sections the navigation offers, by accessible name. */
async function sections() {
  const nav = await screen.findByRole("navigation", { name: "Sections" });
  return ALL.filter((name) => within(nav).queryByRole("link", { name }));
}

describe("what the scopes allow", () => {
  it("shows every section to an owner", async () => {
    renderApp("/journal");
    expect(await sections()).toEqual(ALL);
  });

  it("hides accounts from a guest, and explains it on a direct visit", async () => {
    signInAs("guest");
    renderApp("/accounts");
    expect(await sections()).not.toContain("Comptes");
    expect(await screen.findByRole("heading", { name: "Section réservée" })).toBeInTheDocument();
  });

  it("gives a member only their own corner", async () => {
    signInAs("member");
    renderApp("/journal");
    // reading the household shows its watches and tasks; changing them is for administrators
    expect(await sections()).toEqual([
      "Aujourd'hui",
      "Journal",
      "Personnes",
      "Souvenirs",
      "Veilles",
      "Tâches",
      "Connexions",
    ]);
  });

  it("hides pairing from whoever may only look at satellites", async () => {
    signInAs("member");
    renderApp("/satellites");
    expect(await screen.findByRole("heading", { name: "Section réservée" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approuver…" })).not.toBeInTheDocument();
  });

  it("sends a signed-out visitor to the login page, remembering where they were going", async () => {
    db.signedIn = null;
    const { router } = renderApp("/tasks");
    expect(await screen.findByRole("heading", { name: "Connexion" })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ next: "/tasks" });
  });
});
