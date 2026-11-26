import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("an alert's page", () => {
  it("tells what rings it, why it rang and how it was announced", async () => {
    renderApp("/alerts/a-9d41");
    expect(await screen.findByRole("heading", { name: "School trip reply", level: 1 })).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumbs" });
    expect(within(crumbs).getByRole("link", { name: "Ongoing" })).toHaveAttribute("href", "/activity");
    expect(screen.getByText("Rang once")).toBeInTheDocument();
    expect(screen.getByText("Every time")).toBeInTheDocument();
    const why = screen.getByRole("region", { name: /^Why it rang/ });
    expect(why).toHaveTextContent(
      "“Planetarium trip: reply needed” matched · The school asks for the permission slip.",
    );
    const articles = await screen.findAllByRole("article");
    const chain = articles.find((a) => a.textContent?.includes("rang")) as HTMLElement;
    // the conversation where Léa answered is linked to the alert too, as its own thread
    expect(articles.some((a) => a.textContent?.includes("Put it in the family calendar"))).toBe(true);
    expect(chain).toHaveTextContent("why: Léa is in the living room");
    expect(chain).toHaveTextContent("follow-up");
  });

  it("says which items it waits for, and where each item that rang it came from", async () => {
    const alert = db.alerts.find((a) => a.id === "a-9d41");
    const rang = db.journal.find((e) => e.record.type === "alert.rang" && e.item.links.alert === "a-9d41");
    if (!alert || !rang) throw new Error("the school alert is in the mocks");
    alert.kinds = ["mail", "feed", "github"];
    rang.item.brand = "google";
    renderApp("/alerts/a-9d41");
    const chain = (await screen.findAllByRole("article")).find((a) => a.textContent?.includes("rang"));
    expect(chain).toHaveTextContent("Google");
    expect(screen.getByText("When mail, feeds, github arrive")).toBeInTheDocument();
  });

  it("cancels an alert once confirmed, and goes back to what is ongoing", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/alerts/a-9d41");
    await user.click(await screen.findByRole("button", { name: "Cancel the alert…" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Cancel this alert?" });
    expect(db.alerts.some((a) => a.id === "a-9d41")).toBe(true);
    await user.click(within(dialog).getByRole("button", { name: "Cancel the alert" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/activity"));
    expect(db.alerts.some((a) => a.id === "a-9d41")).toBe(false);
  });
});
