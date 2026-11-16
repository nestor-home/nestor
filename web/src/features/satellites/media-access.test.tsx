import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { SCOPES } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

afterEach(() => server.events.removeAllListeners());

/** The bodies the admin sends to set who may use a device. */
function accessSent(): unknown[] {
  const bodies: unknown[] = [];
  server.events.on("request:start", async ({ request }) => {
    if (request.method === "PUT" && new URL(request.url).pathname.endsWith("/media/access"))
      bodies.push(await request.clone().json());
  });
  return bodies;
}

const section = () => screen.findByRole("region", { name: "Watching and calling" });

describe("who may watch a satellite or call through it", () => {
  it("is shown on the satellite's page, and changed in a dialog", async () => {
    const bodies = accessSent();
    const user = userEvent.setup();
    renderApp("/satellites/reachy-living-room");
    const shown = await section();
    expect(within(shown).getByText("Léa", { selector: "dd" })).toBeVisible(); // may watch
    expect(within(shown).getByText("Jules, Léa")).toBeVisible(); // may call
    await user.click(within(shown).getByRole("button", { name: "Change…" }));
    const dialog = await screen.findByRole("dialog", { name: "Who may use Living room Reachy" });
    expect(within(dialog).queryByRole("checkbox", { name: /Mathis/ })).not.toBeInTheDocument(); // an owner always may
    await user.click(within(dialog).getByRole("checkbox", { name: "Jules may watch" }));
    await user.click(within(dialog).getByRole("checkbox", { name: "Léa may call" }));
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(await section()).findByText("Jules, Léa", { selector: "dd" })).toBeVisible();
    expect(bodies).toEqual([{ viewers: ["jules", "lea"], callers: ["jules"], camera: true }]);
  });

  it("turns the camera off: nobody may be ticked to watch it then", async () => {
    const bodies = accessSent();
    const user = userEvent.setup();
    renderApp("/satellites/reachy-living-room");
    await user.click(within(await section()).getByRole("button", { name: "Change…" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("switch", { name: /Camera on/ }));
    expect(within(dialog).getByRole("checkbox", { name: "Jules may watch" })).toHaveAttribute("aria-disabled", "true");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(await section()).findByText("off")).toBeVisible();
    expect(bodies).toEqual([{ viewers: ["lea"], callers: ["jules", "lea"], camera: false }]);
  });

  it("asks nothing about a camera of a device that does not film", async () => {
    renderApp("/satellites/pi-bedroom");
    const shown = await section();
    expect(within(shown).queryByText("camera")).not.toBeInTheDocument();
    expect(within(shown).getByText("may call")).toBeVisible();
  });

  it("is not shown to whoever only reads the satellites", async () => {
    const admin = SCOPES.admin;
    SCOPES.admin = admin.filter((scope) => scope !== "satellites.manage"); // still reads them through system.read
    db.signedIn = "acc-lea";
    try {
      renderApp("/satellites/reachy-living-room");
      expect(await screen.findByRole("heading", { level: 1, name: /Living room Reachy/ })).toBeVisible();
      expect(screen.queryByRole("region", { name: "Watching and calling" })).not.toBeInTheDocument();
    } finally {
      SCOPES.admin = admin;
    }
  });
});
