import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

/** The people the calls list names, row by row. */
async function callers(): Promise<string[]> {
  const calls = await screen.findByRole("region", { name: "Calls" });
  const rows = await within(calls).findAllByRole("button", { name: /\$|unknown/ });
  return rows.map((row) => row.textContent ?? "");
}

describe("the costs", () => {
  it("keeps one person's calls everywhere below once their row is picked, and lets go of them", async () => {
    const user = userEvent.setup();
    renderApp("/usage");
    const who = await screen.findByRole("region", { name: "Who" });
    const lea = await within(who).findByRole("button", { name: /Léa/ });
    await user.click(lea);
    expect(lea).toHaveAttribute("aria-pressed", "true");
    await waitFor(async () => {
      const rows = await callers();
      expect(rows.length).toBeGreaterThan(0);
      expect(rows.every((row) => row.includes("Léa"))).toBe(true);
    });
    expect(within(who).getByRole("button", { name: /Mathis/ })).toHaveAttribute("aria-pressed", "false");
    const kept = screen.getByRole("button", { name: /Person.*Léa/ });
    await user.click(kept);
    await waitFor(async () => expect((await callers()).some((row) => !row.includes("Léa"))).toBe(true));
  });

  it("shows a member only what their own requests cost", async () => {
    const lea = db.accounts.find((a) => a.id === "acc-lea");
    if (!lea) throw new Error("Léa has an account in the mocks");
    lea.role = "member";
    db.signedIn = "acc-lea";
    renderApp("/usage");
    const who = await screen.findByRole("region", { name: "Who" });
    await waitFor(() =>
      expect(
        within(who)
          .getAllByRole("button")
          .map((b) => b.textContent),
      ).toEqual([expect.stringContaining("Léa")]),
    );
  });

  it("opens a call with what it consumed and where its cost comes from", async () => {
    const user = userEvent.setup();
    renderApp("/usage");
    const calls = await screen.findByRole("region", { name: "Calls" });
    const [first] = await within(calls).findAllByRole("button", { name: /\$/ });
    if (!first) throw new Error("a call is listed");
    await user.click(first);
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByText("Cost")).toBeInTheDocument();
    expect(within(sheet).getByText("Consumed")).toBeInTheDocument();
    expect(within(sheet).getByText(/Billed by the provider|Public price list|Free, on the house/)).toBeInTheDocument();
  });
});
