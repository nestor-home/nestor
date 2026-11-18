/** The house: the household, its rooms and what one reaches through them. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

const part = (name: RegExp) => screen.findByRole("region", { name });

describe("the house", () => {
  it("shows each member with where they are, leading to their page", async () => {
    renderApp("/house");
    const household = await part(/^The household/);
    const mathis = await within(household).findByRole("link", { name: /Mathis/ });
    expect(mathis).toHaveAttribute("href", "/people/mathis");
    expect(mathis).toHaveTextContent("Living room");
    expect(within(household).getByRole("link", { name: /Léa/ })).toHaveTextContent("away");
    expect(within(household).getByRole("link", { name: /Odile/ })).toHaveTextContent("presence unknown");
  });

  it("names a room once, whoever knows it, and opens it in place", async () => {
    const user = userEvent.setup();
    renderApp("/house");
    const rooms = await part(/^The rooms/);
    expect(await within(rooms).findAllByRole("button", { name: /^Kitchen/ })).toHaveLength(1);
    await user.click(within(rooms).getByRole("button", { name: /^Living room/ }));
    const room = await screen.findByRole("dialog", { name: "Living room" });
    expect(within(room).getByText("Mathis, Jules are here.")).toBeInTheDocument();
  });

  it("offers to watch or call only through the devices that can", async () => {
    renderApp("/house");
    const media = await part(/^Watch and call/);
    expect(await within(media).findByRole("button", { name: /^View / })).toBeInTheDocument();
    expect(within(media).getAllByRole("button", { name: /^Call through / }).length).toBeGreaterThan(0);
  });

  it("opens the home system from its state, and does without one when none is plugged in", async () => {
    const user = userEvent.setup();
    const { unmount } = renderApp("/house");
    await user.click(await screen.findByRole("button", { name: /Home system/ }));
    expect(await screen.findByRole("dialog", { name: "Home Assistant" })).toBeInTheDocument();
    unmount();
    db.home = null;
    renderApp("/house");
    await user.click(await screen.findByRole("button", { name: /Home system.*No home system plugged in/ }));
    const sheet = await screen.findByRole("dialog", { name: "Home system" });
    expect(within(sheet).getByRole("link", { name: "Configure" })).toBeInTheDocument();
  });
});
