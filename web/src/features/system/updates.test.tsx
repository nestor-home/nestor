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
  it("shows in the sidebar, and its dialog says what changed and what breaks", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    const dialog = await screen.findByRole("dialog", { name: "Nestor 0.10.0 is here" });
    expect(within(dialog).getByText(/2 releases behind/)).toBeVisible();
    expect(within(dialog).getByRole("alert")).toHaveTextContent("This release changes the data or the configuration");
    const newest = within(dialog).getByRole("region", { name: "Release 0.10.0" });
    expect(within(newest).getByText("Breaking changes")).toBeVisible();
    expect(within(newest).getByText("the admin says when a newer Nestor is out")).toBeVisible();
    expect(within(newest).getByRole("link", { name: /Release notes/ })).toHaveAttribute(
      "href",
      "https://github.com/nestor-home/nestor/releases/tag/v0.10.0",
    );
  });

  it("installs the newest release once the owner confirms, then follows the install", async () => {
    const user = userEvent.setup();
    const sent = requests("/system/updates/install");
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    const dialog = await screen.findByRole("dialog", { name: "Nestor 0.10.0 is here" });
    await user.click(within(dialog).getByRole("button", { name: "Install 0.10.0" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Install Nestor 0.10.0?" });
    expect(screen.queryByRole("dialog", { name: "Nestor 0.10.0 is here" })).toBeNull();
    expect(within(confirm).getByText(/it stays on 0\.9\.0/)).toBeVisible();
    expect(sent).toHaveLength(0);
    await user.click(within(confirm).getByRole("button", { name: "Install and restart" }));
    const following = await screen.findByRole("dialog", { name: "Nestor 0.10.0 is here" });
    expect(await within(following).findByText("Installing 0.10.0…")).toBeVisible();
    expect(sent).toHaveLength(1);
  });

  it("follows Nestor through its restart, once it is back on the release and lists nothing newer", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    const dialog = await screen.findByRole("dialog", { name: "Nestor 0.10.0 is here" });
    await user.click(within(dialog).getByRole("button", { name: "Install 0.10.0" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Install and restart" }),
    );
    // the mock installs, then restarts on 0.10.0 (no newer release) and signs everyone out
    expect(await screen.findByText("Restarting, back in a moment.", {}, { timeout: 8_000 })).toBeVisible();
  }, 15_000);

  it("goes back to the notes when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Install 0.10.0" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancel" }));
    expect(await screen.findByRole("dialog", { name: "Nestor 0.10.0 is here" })).toBeVisible();
  });

  it("gives the commands where Nestor cannot install itself, then the restart", async () => {
    const user = userEvent.setup();
    db.updates = { ...db.updates, installable: false };
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByRole("button", { name: /Install/ })).toBeNull();
    expect(within(dialog).getByText("pip install --upgrade 'nestor-home[voice]'")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Restart now" })).toBeEnabled();
  });

  it("says when a release did not install", async () => {
    const user = userEvent.setup();
    db.updates = { ...db.updates, failed: "0.10.0" };
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("0.10.0 did not install. Nestor stays on 0.9.0.")).toBeVisible();
  });

  it("says which satellites the new version leaves behind, and the image's commands in a container", async () => {
    const user = userEvent.setup();
    db.updates = {
      ...db.updates,
      left_behind: [{ id: "reachy-office", name: null }],
      installation: "container",
      commands: ["docker compose pull", "docker compose up -d"],
      installable: false,
    };
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: /New release/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("This satellite will no longer connect: update it first.")).toBeVisible();
    expect(within(dialog).getByText("reachy-office")).toBeVisible();
    expect(within(dialog).getByText("docker compose pull")).toBeVisible();
    expect(within(dialog).queryByRole("button", { name: "Restart now" })).toBeNull();
  });

  it("stays out of the way when the running version is the latest", async () => {
    db.updates = { ...db.updates, releases: [] };
    renderApp("/");
    expect(await screen.findByRole("navigation")).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("button", { name: /New release/ })).toBeNull());
  });
});

describe("updating a satellite", () => {
  it("opens from the satellite's page, says what changes and what happens, then installs", async () => {
    const user = userEvent.setup();
    const sent = requests("/satellites/reachy-living-room/update");
    renderApp("/satellites/reachy-living-room");
    await user.click(await screen.findByRole("button", { name: "Update available" }));
    const dialog = await screen.findByRole("dialog", { name: "Living room Reachy: version 0.4.1" });
    expect(within(dialog).getByRole("link", { name: /What changes in 0\.4\.1/ })).toHaveAttribute(
      "href",
      "https://github.com/nestor-home/nestor-reachy/releases/tag/v0.4.1",
    );
    expect(within(dialog).getByText(/goes back to 0\.4\.0 by itself/)).toBeVisible();
    expect(sent).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Update to 0.4.1" }));
    expect(await screen.findByText("Living room Reachy is updating.")).toBeVisible();
    expect(await within(dialog).findByText("Installing 0.4.1…")).toBeVisible();
    expect(await screen.findByRole("button", { name: "Updating…", hidden: true })).toBeInTheDocument();
    expect(sent).toHaveLength(1);
  });

  it("says when a version did not start, and offers no install then", async () => {
    const user = userEvent.setup();
    const living = db.satellites.find((s) => s.id === "reachy-living-room");
    if (!living) throw new Error("fixture changed");
    living.update = { state: "failed", version: "0.4.1", notes: null };
    renderApp("/satellites/reachy-living-room");
    await user.click(await screen.findByRole("button", { name: "Update failed" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("0.4.1 did not start, so it went back to its version.")).toBeVisible();
    expect(within(dialog).getByText("The device gave no release notes for this version.")).toBeVisible();
    expect(within(dialog).queryByRole("button", { name: /Update to/ })).toBeNull();
  });

  it("shows no update button for a satellite that cannot update or is up to date", async () => {
    renderApp("/satellites/reachy-office");
    expect(await screen.findByRole("heading", { level: 1 })).toBeVisible();
    expect(screen.queryByRole("button", { name: /Update/ })).toBeNull();
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
