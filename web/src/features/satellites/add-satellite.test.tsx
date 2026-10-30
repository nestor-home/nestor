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
  await user.click(await screen.findByRole("button", { name: "Ajouter un satellite" }));
  const sheet = await screen.findByRole("dialog", { name: "Ajouter un satellite" });
  await within(sheet).findByRole("button", { name: /Code sur son écran/ });
  return { user, sheet };
}

describe("adding a satellite", () => {
  it("lists every method, the recommended one first and chosen", async () => {
    const { sheet } = await openAdd();
    const methods = within(sheet)
      .getAllByRole("button")
      .filter((b) => b.hasAttribute("aria-pressed"));
    expect(methods.map((m) => m.textContent)).toEqual([
      expect.stringMatching(/^Code sur son écranrecommandé/),
      expect.stringMatching(/^Code dit à voix haute/),
      expect.stringMatching(/^QR code/),
      expect.stringMatching(/^Code saisi sur l'appareil/),
      expect.stringMatching(/^Configuration/),
    ]);
    expect(methods[0]).toHaveAttribute("aria-pressed", "true");
  });

  it("gives an enrollment code to paste, then follows the device until it is paired", async () => {
    const { user, sheet } = await openAdd();
    await user.click(within(sheet).getByRole("button", { name: /^Configuration/ }));
    await user.type(within(sheet).getByLabelText("Nom"), "Reachy de la véranda");
    await user.type(within(sheet).getByLabelText("Pièce"), "Véranda");
    expect(within(sheet).getByText("Enregistrée comme « veranda ».")).toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Commencer" }));

    const [code] = await within(sheet).findAllByText(/^[0-9A-Z]{4}-[0-9A-Z]{4}$/);
    const canonical = code?.textContent?.replace("-", "") ?? "";
    expect(within(sheet).getByRole("img", { name: /QR code de l'adresse d'appairage/ })).toBeInTheDocument();
    expect(sheet).toHaveTextContent(`NESTOR_PAIRING_URI="nestor+http://nestor.local:7860/?code=${canonical}"`);
    expect(sheet).toHaveTextContent(`nestor-satellite run --pairing-uri`);
    expect(within(sheet).getByRole("list", { name: "Avancement de l'ajout" })).toHaveTextContent(
      "en attente de l'appareil",
    );
    expect(db.additions[0]).toMatchObject({
      method: "enrollment.provisioning",
      name: "Reachy de la véranda",
      room: "veranda",
    });

    deviceTurnsUp();
    expect(
      await within(sheet).findByText("Reachy de la véranda est appairé.", {}, { timeout: 5_000 }),
    ).toBeInTheDocument();
    expect(db.satellites.find((s) => s.name === "Reachy de la véranda")?.room).toBe("veranda");
  });

  it("waits for a device to ask, identifies it, then pairs it with the code it says", async () => {
    const { user, sheet } = await openAdd();
    await user.click(within(sheet).getByRole("button", { name: /^Code dit à voix haute/ }));
    await user.click(within(sheet).getByRole("button", { name: "Commencer" }));
    expect(await within(sheet).findByText(/J'attends que l'appareil se présente/)).toBeInTheDocument();

    deviceTurnsUp();
    const candidate = await within(sheet).findByText("reachy-mini-veranda", {}, { timeout: 5_000 });
    expect(candidate).toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Identifier" }));
    expect(await screen.findByText("Demandé : l'appareil se signale dans un instant.")).toBeInTheDocument();

    await user.type(within(sheet).getByLabelText("Code affiché par l'appareil"), "424 242");
    await user.click(within(sheet).getByRole("button", { name: "Appairer" }));
    await waitFor(() => expect(db.satellites.some((s) => s.id === "reachy-mini-veranda")).toBe(true));
    expect(db.additions[0]?.status).toBe("completed");
  });

  it("cancels an addition: its code no longer pairs anything", async () => {
    const { user, sheet } = await openAdd();
    await user.click(within(sheet).getByRole("button", { name: /^QR code/ }));
    await user.click(within(sheet).getByRole("button", { name: "Commencer" }));
    await within(sheet).findAllByText(/^[0-9A-Z]{4}-[0-9A-Z]{4}$/);
    await user.click(within(sheet).getByRole("button", { name: "Annuler l'ajout" }));
    expect(await screen.findByText("Ajout annulé : son code n'appaire plus rien.")).toBeInTheDocument();
    expect(db.additions[0]?.status).toBe("cancelled");
  });

  it("turns a room into the slug the API takes", () => {
    expect(roomSlug("Chambre de Jules")).toBe("chambre-de-jules");
    expect(roomSlug("  Véranda ")).toBe("veranda");
  });
});
