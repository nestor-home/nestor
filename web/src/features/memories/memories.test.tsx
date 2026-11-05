import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("memories", () => {
  it("corrects a memory in a dialog, and links to where it was learnt", async () => {
    const user = userEvent.setup();
    renderApp("/memories?about=jules");
    const card = (await screen.findByText("Jules has handball practice on Wednesdays at 3 pm.")).closest(
      "li",
    ) as HTMLElement;
    expect(within(card).getByRole("link", { name: /source/ })).toHaveAttribute(
      "href",
      expect.stringContaining("session=s-jules"),
    );
    const allergy = (await screen.findByText("Jules is allergic to peanuts.")).closest("li") as HTMLElement;
    await user.click(within(allergy).getByRole("button", { name: "Correct…" }));
    const dialog = await screen.findByRole("dialog", { name: "Correct the memory" });
    const text = within(dialog).getByLabelText("Memory text");
    await user.clear(text);
    await user.type(text, "Jules is allergic to peanuts and cashews.");
    await user.keyboard("{Meta>}{Enter}{/Meta}");
    expect(await screen.findByText("Memory corrected.")).toBeInTheDocument();
    expect(db.memories.find((m) => m.id === "m-01")?.text).toContain("cashews");
  });

  it("forgets a memory only once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/memories");
    const card = (await screen.findByText(/Odile comes for lunch/)).closest("li") as HTMLElement;
    await user.click(within(card).getByRole("button", { name: "Forget…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Forget" }));
    await waitFor(() => expect(screen.queryByText(/Odile comes for lunch/)).not.toBeInTheDocument());
    expect(db.memories.some((m) => m.id === "m-04")).toBe(false);
  });

  it("searches and says when nothing matches", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/memories");
    await user.type(await screen.findByLabelText("Search"), "piscine");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No memory matches.")).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ q: "piscine" });
  });
});
