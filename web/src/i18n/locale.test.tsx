import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

/** The browser's languages, as a person's settings would give them. */
function browserReads(...languages: string[]): void {
  Object.defineProperty(window.navigator, "languages", { value: languages, configurable: true });
  Object.defineProperty(window.navigator, "language", { value: languages[0], configurable: true });
}

describe("the admin's language", () => {
  afterEach(() => browserReads("en-US", "en"));

  it("follows the account, then switches from the account menu, server texts and household included", async () => {
    const user = userEvent.setup();
    renderApp("/journal");
    const nav = await screen.findByRole("navigation", { name: "Sections" });
    expect(within(nav).getByRole("link", { name: "Today" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
    expect((await screen.findAllByText(/Jules is in the living room/)).length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("button", { name: /Account menu/ })[0] as HTMLElement);
    await user.click(await screen.findByRole("menuitemradio", { name: "Français" }));

    expect(await screen.findByRole("link", { name: "Aujourd'hui" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("fr");
    await waitFor(() => expect(db.accounts.find((a) => a.id === "acc-mathis")?.locale).toBe("fr"));
    // the journal's lines come back rendered by the server in French, the household's rooms too
    expect((await screen.findAllByText(/Jules est dans la pièce « salon »/)).length).toBeGreaterThan(0);
  });

  it("uses the browser's language for an account without one", async () => {
    browserReads("fr-FR", "fr");
    renderApp("/journal");
    expect(await screen.findByRole("link", { name: "Aujourd'hui" })).toBeInTheDocument();
    expect((await screen.findAllByText(/Jules est dans la pièce « salon »/)).length).toBeGreaterThan(0);
  });
});
