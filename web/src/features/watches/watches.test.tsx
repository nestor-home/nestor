import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("a watch's page", () => {
  it("tells what a watch found and how it was announced", async () => {
    renderApp("/watches/w-9d41");
    expect(await screen.findByRole("heading", { name: /News from the school/, level: 1 })).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumbs" });
    expect(within(crumbs).getByRole("link", { name: "Ongoing" })).toHaveAttribute("href", "/activity");
    expect(screen.getByText("1 trigger")).toBeInTheDocument();
    expect(screen.getByText("Reports every relevant message.")).toBeInTheDocument();
    const articles = await screen.findAllByRole("article");
    const chain = articles.find((a) => a.textContent?.includes("triggered")) as HTMLElement;
    // the conversation where Léa answered is linked to the watch too, as its own thread
    expect(articles.some((a) => a.textContent?.includes("Put it in the family calendar"))).toBe(true);
    expect(chain).toHaveTextContent("why: Léa is in the living room");
    expect(chain).toHaveTextContent("follow-up");
  });

  it("says what each watch watches, and where each item it found came from", async () => {
    const watch = db.watches.find((w) => w.id === "w-9d41");
    const triggered = db.journal.find((e) => e.record.type === "watch.triggered" && e.item.links.watch === "w-9d41");
    if (!watch || !triggered) throw new Error("the school watch is in the mocks");
    watch.kinds = ["mail", "feed", "github"];
    triggered.item.brand = "google";
    renderApp("/watches/w-9d41");
    const chain = (await screen.findAllByRole("article")).find((a) => a.textContent?.includes("triggered"));
    expect(chain).toHaveTextContent("Google");
    for (const kind of ["mail", "feeds", "github"]) expect(screen.getByText(kind)).toBeInTheDocument();
  });

  it("cancels a watch once confirmed, and goes back to what is ongoing", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/watches/w-9d41");
    await user.click(await screen.findByRole("button", { name: "Cancel the watch…" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Cancel this watch?" });
    expect(db.watches.some((w) => w.id === "w-9d41")).toBe(true);
    await user.click(within(dialog).getByRole("button", { name: "Cancel the watch" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/activity"));
    expect(db.watches.some((w) => w.id === "w-9d41")).toBe(false);
  });
});
