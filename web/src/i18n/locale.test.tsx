import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("the admin's language", () => {
  it("follows the account, then switches from the account menu, server texts included", async () => {
    const user = userEvent.setup();
    renderApp("/journal");
    const nav = await screen.findByRole("navigation", { name: "Sections" });
    expect(within(nav).getByRole("link", { name: "Aujourd'hui" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("fr");
    expect((await screen.findAllByText(/Jules est dans la pièce « salon »/)).length).toBeGreaterThan(0);

    await user.click(screen.getAllByRole("button", { name: /Menu du compte/ })[0] as HTMLElement);
    await user.click(await screen.findByRole("menuitemradio", { name: "English" }));

    expect(await screen.findByRole("link", { name: "Today" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
    await waitFor(() => expect(db.accounts.find((a) => a.id === "acc-mathis")?.locale).toBe("en"));
    // the journal's lines come back rendered by the server in English
    expect((await screen.findAllByText(/Jules is in the salon/)).length).toBeGreaterThan(0);
  });

  it("uses the browser's language for an account without one", async () => {
    const account = db.accounts.find((a) => a.id === "acc-mathis");
    if (account) account.locale = null;
    renderApp("/journal");
    expect(await screen.findByRole("link", { name: "Aujourd'hui" })).toBeInTheDocument();
  });
});
