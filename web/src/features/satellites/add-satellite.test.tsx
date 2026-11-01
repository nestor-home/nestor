import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { DEVICE_TURNS_UP_S } from "@/mocks/handlers";
import { renderApp } from "@/test/render";
import { roomSlug } from "./add-satellite";

/** What happens on the network while the person watches: the device turns up now. */
function deviceTurnsUp() {
  for (const a of db.additions) a.created_at = new Date(Date.now() - (DEVICE_TURNS_UP_S + 1) * 1000).toISOString();
}

async function openAdd() {
  const user = userEvent.setup();
  renderApp("/satellites");
  await user.click(await screen.findByRole("button", { name: "Add a satellite" }));
  const sheet = await screen.findByRole("dialog", { name: "Add a satellite" });
  await within(sheet).findByRole("button", { name: /Code on its screen/ });
  return { user, sheet };
}

describe("adding a satellite", () => {
  it("lists every method, the recommended one first and chosen", async () => {
    const { sheet } = await openAdd();
    const methods = within(sheet)
      .getAllByRole("button")
      .filter((b) => b.hasAttribute("aria-pressed"));
    expect(methods.map((m) => m.textContent)).toEqual([
      expect.stringMatching(/^Code on its screenrecommended/),
      expect.stringMatching(/^Code said aloud/),
      expect.stringMatching(/^QR code/),
      expect.stringMatching(/^Code typed on the device/),
      expect.stringMatching(/^Configuration/),
    ]);
    expect(methods[0]).toHaveAttribute("aria-pressed", "true");
  });

  it("gives an enrollment code to paste, then follows the device until it is paired", async () => {
    const { user, sheet } = await openAdd();
    await user.click(within(sheet).getByRole("button", { name: /^Configuration/ }));
    await user.type(within(sheet).getByLabelText("Name"), "Veranda Reachy");
    await user.type(within(sheet).getByLabelText("Room"), "Veranda");
    expect(within(sheet).getByText("Saved as “veranda”.")).toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Start" }));

    const [code] = await within(sheet).findAllByText(/^[0-9A-Z]{4}-[0-9A-Z]{4}$/);
    const canonical = code?.textContent?.replace("-", "") ?? "";
    expect(within(sheet).getByRole("img", { name: /QR code of the pairing address/ })).toBeInTheDocument();
    expect(sheet).toHaveTextContent(`NESTOR_PAIRING_URI="nestor+http://nestor.local:7860/?code=${canonical}"`);
    expect(sheet).toHaveTextContent(`nestor-satellite run --pairing-uri`);
    expect(within(sheet).getByRole("list", { name: "Progress of the addition" })).toHaveTextContent(
      "waiting for the device",
    );
    expect(db.additions[0]).toMatchObject({
      method: "enrollment.provisioning",
      name: "Veranda Reachy",
      room: "veranda",
    });

    deviceTurnsUp();
    expect(await within(sheet).findByText("Veranda Reachy is paired.", {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(db.satellites.find((s) => s.name === "Veranda Reachy")?.room).toBe("veranda");
  });

  it("waits for a device to ask, identifies it, then pairs it with the code it says", async () => {
    const { user, sheet } = await openAdd();
    await user.click(within(sheet).getByRole("button", { name: /^Code said aloud/ }));
    await user.click(within(sheet).getByRole("button", { name: "Start" }));
    expect(await within(sheet).findByText(/I'm waiting for the device to turn up/)).toBeInTheDocument();

    deviceTurnsUp();
    const candidate = await within(sheet).findByText("reachy-mini-veranda", {}, { timeout: 5_000 });
    expect(candidate).toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Identify" }));
    expect(await screen.findByText("Asked: the device makes itself noticed in a moment.")).toBeInTheDocument();

    await user.type(within(sheet).getByLabelText("Code shown by the device"), "424 242");
    await user.click(within(sheet).getByRole("button", { name: "Pair" }));
    await waitFor(() => expect(db.satellites.some((s) => s.id === "reachy-mini-veranda")).toBe(true));
    expect(db.additions[0]?.status).toBe("completed");
  });

  it("cancels an addition: its code no longer pairs anything", async () => {
    const { user, sheet } = await openAdd();
    await user.click(within(sheet).getByRole("button", { name: /^QR code/ }));
    await user.click(within(sheet).getByRole("button", { name: "Start" }));
    await within(sheet).findAllByText(/^[0-9A-Z]{4}-[0-9A-Z]{4}$/);
    await user.click(within(sheet).getByRole("button", { name: "Cancel the addition" }));
    expect(await screen.findByText("Addition cancelled: its code no longer pairs anything.")).toBeInTheDocument();
    expect(db.additions[0]?.status).toBe("cancelled");
  });

  it("turns a room into the slug the API takes", () => {
    expect(roomSlug("Chambre de Jules")).toBe("chambre-de-jules");
    expect(roomSlug("  Véranda ")).toBe("veranda");
  });
});
