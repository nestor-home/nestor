import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("the command palette", () => {
  it("opens with ⌘K, filters as you type and goes where you pick", async () => {
    db.signedIn = "acc-mathis";
    const user = userEvent.setup();
    renderApp("/");
    await screen.findByRole("navigation", { name: "Sections" });

    await user.keyboard("{Meta>}k{/Meta}");
    const search = await screen.findByRole("combobox");
    await user.type(search, "satel");
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("heading", { level: 1, name: "Satellites" })).toBeInTheDocument();
  });
});
