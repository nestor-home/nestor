import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("a newer Nestor", () => {
  it("shows in the sidebar, and its dialog says what changed and what breaks", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    const dialog = await screen.findByRole("dialog", { name: "Nestor 0.10.0 is here" });
    expect(within(dialog).getByText(/2 releases behind/)).toBeVisible();
    expect(within(dialog).getByRole("alert")).toHaveTextContent("This release changes the data or the configuration");
    expect(within(dialog).getByText("Update Nestor the way you installed it, then restart it.")).toBeVisible();
    const newest = within(dialog).getByRole("region", { name: "Release 0.10.0" });
    expect(within(newest).getByText("Breaking changes")).toBeVisible();
    expect(within(newest).getByText("the admin says when a newer Nestor is out")).toBeVisible();
    expect(within(newest).getByRole("link", { name: /Release notes/ })).toHaveAttribute(
      "href",
      "https://github.com/nestor-home/nestor/releases/tag/v0.10.0",
    );
  });

  it("stays out of the way when the running version is the latest", async () => {
    db.updates = { ...db.updates, releases: [] };
    renderApp("/");
    expect(await screen.findByRole("navigation")).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("button", { name: /New release/ })).toBeNull());
  });
});
