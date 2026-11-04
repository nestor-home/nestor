import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

function requests(path: string) {
  const sent: string[] = [];
  server.events.on("request:start", ({ request }) => {
    if (request.method === "POST" && new URL(request.url).pathname.endsWith(path)) sent.push(request.url);
  });
  return sent;
}

describe("a newer Nestor", () => {
  it("shows in the sidebar, and its dialog says what changed, what breaks and how to update", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    const dialog = await screen.findByRole("dialog", { name: "Nestor 0.10.0 is out" });
    expect(within(dialog).getByText("You run 0.9.0, 2 releases behind. Here is what changed since.")).toBeVisible();
    expect(within(dialog).getByRole("alert")).toHaveTextContent("This release changes the data or the configuration");
    const newest = within(dialog).getByRole("region", { name: "Release 0.10.0" });
    expect(within(newest).getByText("Breaking changes")).toBeVisible();
    expect(within(newest).getByText("the admin says when a newer Nestor is out")).toBeVisible();
    expect(within(newest).getByRole("link", { name: /Release notes/ })).toHaveAttribute(
      "href",
      "https://github.com/nestor-home/nestor/releases/tag/v0.10.0",
    );
    expect(within(dialog).getByText("uv tool upgrade nestor-home")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Restart now" })).toBeEnabled();
  });

  it("says which satellites the new version leaves behind, and the image's commands in a container", async () => {
    const user = userEvent.setup();
    db.updates = { ...db.updates, outdated_satellites: ["reachy-office"], container: true };
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("This satellite will no longer connect: update it first.")).toBeVisible();
    expect(within(dialog).getByText("reachy-office")).toBeVisible();
    expect(within(dialog).getByText("docker compose pull")).toBeVisible();
    expect(within(dialog).queryByRole("button", { name: "Restart now" })).toBeNull();
  });

  it("stays out of the way when the running version is the latest", async () => {
    db.updates = { ...db.updates, latest: "0.9.0", releases: [] };
    renderApp("/");
    expect(await screen.findByRole("navigation")).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("button", { name: /New release/ })).toBeNull());
  });
});

describe("updating a satellite", () => {
  it("installs the version the satellite reported, once a person confirms, and follows it", async () => {
    const user = userEvent.setup();
    const sent = requests("/satellites/reachy-living-room/update");
    renderApp("/satellites/reachy-living-room");
    const update = await screen.findByRole("region", { name: "Update" });
    expect(within(update).getByText(/Version 0\.4\.1 is out; it runs 0\.4\.0/)).toBeVisible();
    await user.click(within(update).getByRole("button", { name: "Update to 0.4.1" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Update Living room Reachy to 0.4.1?" });
    expect(sent).toHaveLength(0);
    await user.click(within(confirm).getByRole("button", { name: "Update" }));
    expect(await screen.findByText("Living room Reachy is installing 0.4.1.")).toBeVisible();
    expect(await screen.findByText("installing 0.4.1…")).toBeVisible();
    expect(sent).toHaveLength(1);
  });

  it("says when a version did not start, and offers nothing to a satellite that cannot update", async () => {
    const living = db.satellites.find((s) => s.id === "reachy-living-room");
    if (!living) throw new Error("fixture changed");
    living.update = { state: "failed", version: "0.4.1" };
    renderApp("/satellites/reachy-living-room");
    expect(
      await screen.findByText("Version 0.4.1 did not start: the satellite went back to the previous one."),
    ).toBeVisible();
    expect(screen.queryByRole("button", { name: /Update to/ })).toBeNull();
  });

  it("marks the satellites with an update in the list", async () => {
    renderApp("/satellites");
    const row = await screen.findByRole("link", { name: /Living room Reachy/ });
    expect(within(row).getByText("update available")).toBeVisible();
    expect(
      within(await screen.findByRole("link", { name: /Jules's speaker/ })).queryByText("update available"),
    ).toBeNull();
  });
});
