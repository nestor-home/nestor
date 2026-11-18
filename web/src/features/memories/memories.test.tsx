import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("memories", () => {
  it("sorts what the agent knows under whom it is about", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/memories");
    const jules = await screen.findByRole("region", { name: /^Jules/ });
    expect(within(jules).getByRole("button", { name: /Jules is allergic to peanuts\./ })).toBeInTheDocument();
    expect(within(jules).queryByText(/Odile comes for lunch/)).not.toBeInTheDocument();
    expect(within(jules).getByRole("link", { name: "Open Jules's page" })).toHaveAttribute("href", "/people/jules");
    await user.click(screen.getByRole("button", { name: "Odile" }));
    await waitFor(() => expect(router.state.location.search).toEqual({ about: "odile" }));
    expect(await screen.findByText(/Odile comes for lunch/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Jules is allergic to peanuts.")).not.toBeInTheDocument());
  });

  it("opens a memory to say where it was learnt, and corrects it in a dialog", async () => {
    const user = userEvent.setup();
    renderApp("/memories?about=jules");
    await user.click(await screen.findByRole("button", { name: /Jules has handball practice on Wednesdays/ }));
    const practice = await screen.findByRole("dialog", { name: /Jules has handball practice/ });
    expect(within(practice).getByRole("link", { name: /Where it was learnt/ })).toHaveAttribute(
      "href",
      expect.stringContaining("session=s-jules"),
    );
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: /Jules is allergic to peanuts\./ }));
    const allergy = await screen.findByRole("dialog", { name: "Jules is allergic to peanuts." });
    await user.click(within(allergy).getByRole("button", { name: "Correct…" }));
    const dialog = await screen.findByRole("dialog", { name: "Correct the memory" });
    const text = within(dialog).getByLabelText("Memory text");
    await user.clear(text);
    await user.type(text, "Jules is allergic to peanuts and cashews.");
    await user.keyboard("{Meta>}{Enter}{/Meta}");
    expect(await screen.findByText("Memory corrected.")).toBeInTheDocument();
    expect(db.memories.find((m) => m.id === "m-01")?.text).toContain("cashews");
    expect(
      await screen.findByRole("dialog", { name: "Jules is allergic to peanuts and cashews." }),
    ).toBeInTheDocument();
  });

  it("forgets a memory only once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/memories");
    await user.click(await screen.findByRole("button", { name: /Odile comes for lunch/ }));
    const sheet = await screen.findByRole("dialog", { name: /Odile comes for lunch/ });
    await user.click(within(sheet).getByRole("button", { name: "Forget…" }));
    expect(db.memories.some((m) => m.id === "m-04")).toBe(true);
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Forget" }));
    await waitFor(() => expect(screen.queryByText(/Odile comes for lunch/)).not.toBeInTheDocument());
    expect(db.memories.some((m) => m.id === "m-04")).toBe(false);
  });

  it("searches in a dialog, says when nothing matches, and clears the search", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/memories");
    await user.click(await screen.findByRole("button", { name: "Search…" }));
    const dialog = await screen.findByRole("dialog", { name: "Search the memories" });
    await user.type(within(dialog).getByLabelText("Search"), "piscine");
    await user.click(within(dialog).getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No memory matches.")).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ q: "piscine" });
    await user.click(screen.getByRole("button", { name: "Clear the search" }));
    expect(await screen.findByRole("region", { name: /^Jules/ })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({});
  });
});
