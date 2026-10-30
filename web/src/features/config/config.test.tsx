import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

const saveBar = () => screen.findByRole("region", { name: "Modifications non enregistrées" });

describe("the configuration", () => {
  it("renders every kind of setting with its control", async () => {
    const user = userEvent.setup();
    renderApp("/config/tools");
    await user.click(await screen.findByRole("button", { name: "Modifier maison" }));
    const sheet = await screen.findByRole("dialog", { name: "maison" });
    expect(within(sheet).getByRole("textbox", { name: "Adresse" })).toHaveValue(
      "http://homeassistant.local:8123/mcp_server/sse",
    );
    expect(within(sheet).getByRole("combobox", { name: "Transport" })).toHaveTextContent("sse");
    expect(within(sheet).getByText(`référence \${secret:tools.maison.token}`)).toBeInTheDocument();
    const timeout = within(sheet).getByRole("spinbutton", { name: "Délai (secondes)" });
    expect(timeout).toHaveAttribute("placeholder", "10");
    expect(timeout).toHaveAttribute("min", "0");
    expect(within(sheet).getByRole("textbox", { name: "Risks, nom 1" })).toHaveValue("HassTurnOff");
  });

  it("keeps a secret unless it is replaced, and never shows its value", async () => {
    const user = userEvent.setup();
    renderApp("/config/model");
    const panel = (await screen.findAllByText(`référence \${secret:model.api_key}`))[0];
    expect(panel).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Remplacer Clé d'API" })[0] as HTMLElement);
    const field = screen.getAllByLabelText("Clé d'API")[0] as HTMLInputElement;
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveValue("");
    await user.type(field, "sk-or-v1-new");
    await user.click(await screen.findByRole("button", { name: "1 modification" }));
    const changes = await screen.findByRole("dialog", { name: "Modifications" });
    expect(within(changes).getByText("model.api_key")).toBeInTheDocument();
    expect(within(changes).getByText("secret modifié")).toBeInTheDocument();
    expect(changes).not.toHaveTextContent("sk-or-v1-new");
    await user.keyboard("{Escape}");
    await user.click(screen.getAllByRole("button", { name: "Garder l'actuel" })[0] as HTMLElement);
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Modifications non enregistrées" })).not.toBeInTheDocument(),
    );
  });

  it("folds the advanced settings until asked", async () => {
    const user = userEvent.setup();
    renderApp("/config/initiative");
    expect(await screen.findByLabelText("Heures calmes")).toHaveValue("22:30-07:30");
    expect(screen.queryByLabelText("Relance écrite après (secondes)")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Avancé · 1 réglage" }));
    expect(screen.getByLabelText("Relance écrite après (secondes)")).toBeVisible();
  });

  it("adds to and removes from a list", async () => {
    const user = userEvent.setup();
    renderApp("/config/household");
    await user.click(await screen.findByRole("button", { name: "Modifier Jules" }));
    const sheet = await screen.findByRole("dialog", { name: "Jules" });
    await user.click(within(sheet).getByRole("button", { name: "Ajouter" }));
    await user.type(
      within(sheet).getByRole("textbox", { name: "Comptes sur les canaux, élément 2" }),
      "telegram:@jules",
    );
    await user.click(within(sheet).getByRole("button", { name: "Terminé" }));
    await user.click(await screen.findByRole("button", { name: "1 modification" }));
    const changes = await screen.findByRole("dialog", { name: "Modifications" });
    expect(within(changes).getByText("household.2.accounts.1")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: "Modifier Jules" }));
    const again = await screen.findByRole("dialog", { name: "Jules" });
    await user.click(within(again).getByRole("button", { name: "Retirer telegram:@jules" }));
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Modifications non enregistrées" })).not.toBeInTheDocument(),
    );
  });

  it("shows a problem at its field, and on the page that holds it", async () => {
    const user = userEvent.setup();
    renderApp("/config/channels");
    await user.click(await screen.findByRole("button", { name: "Modifier Voix" }));
    const sheet = await screen.findByRole("dialog", { name: "Voix" });
    await user.clear(within(sheet).getByRole("textbox", { name: "Pièce" }));
    expect(await within(sheet).findByText("Pièce : ne peut pas être vide")).toBeInTheDocument();
    expect(within(sheet).getByRole("textbox", { name: "Pièce" })).toHaveAttribute("aria-invalid", "true");
    await user.click(within(sheet).getByRole("button", { name: "Terminé" }));
    expect(within(await saveBar()).getByRole("button", { name: "1 problème" })).toBeInTheDocument();
    expect(within(await saveBar()).getByRole("button", { name: "Enregistrer" })).toBeDisabled();
    expect(screen.getByRole("link", { name: /Canaux\s*1/ })).toBeInTheDocument();
  });

  it("puts what the server refuses at its field when saving", async () => {
    server.use(
      http.put("/api/v1/config", () =>
        HttpResponse.json(
          {
            error: {
              code: "config_invalid",
              message_id: "error-config-invalid",
              args: { count: 1 },
              message: "La configuration est inutilisable (un problème) : rien n'a été écrit.",
              problems: [
                {
                  path: ["persona", "timezone"],
                  code: "invalid",
                  message_id: "config-error-invalid",
                  args: { path: "persona.timezone", detail: "fuseau inconnu" },
                  message: "persona.timezone : fuseau inconnu",
                },
              ],
            },
          },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderApp("/config/persona");
    const zone = await screen.findByRole("textbox", { name: "Fuseau horaire" });
    await user.clear(zone);
    await user.type(zone, "Mars/Olympus");
    const bar = await saveBar();
    await waitFor(() => expect(within(bar).getByRole("button", { name: "Enregistrer" })).toBeEnabled());
    await user.click(within(bar).getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText("Fuseau horaire : fuseau inconnu")).toBeInTheDocument();
    expect(db.config.restart_required).toBe(false);
  });

  it("saves, then asks for a restart that a person starts, and reconnects", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/config/persona");
    const name = await screen.findByRole("textbox", { name: "Nom" });
    await user.clear(name);
    await user.type(name, "Alfred");
    const bar = await saveBar();
    await waitFor(() => expect(within(bar).getByRole("button", { name: "Enregistrer" })).toBeEnabled());
    await user.click(within(bar).getByRole("button", { name: "Enregistrer" }));
    expect(await screen.findByText("Redémarrage requis")).toBeInTheDocument();
    expect(screen.getByText(/1 changement en attente/)).toBeInTheDocument();
    expect(db.config.restart_required).toBe(true);
    // nothing restarts by itself
    expect(screen.getByRole("link", { name: /Richie/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Redémarrer…" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Redémarrer Richie ?" });
    expect(dialog).toHaveTextContent("Les canaux se ferment");
    expect(dialog).toHaveTextContent("Les tâches confiées à distance continuent");
    await user.click(within(dialog).getByRole("button", { name: "Redémarrer maintenant" }));
    expect(await screen.findByText("Je redémarre, à tout de suite.")).toBeInTheDocument();
    // sessions live in the process's memory: the restarted instance asks to sign in again, then comes back
    expect(await screen.findByText(/Me revoilà, configuration appliquée/, {}, { timeout: 8_000 })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Connexion" })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ next: "/config/persona" });
    await user.type(screen.getByLabelText("Identifiant"), "mathis");
    await user.type(screen.getByLabelText("Mot de passe"), "nestor");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByRole("link", { name: /Alfred/ })).toBeInTheDocument();
    expect(screen.queryByText("Redémarrage requis")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/config/persona");
  }, 20_000);

  it("explains why a secret in use is not deleted, and deletes it only when insisted", async () => {
    const user = userEvent.setup();
    renderApp("/config/secrets");
    await user.click(await screen.findByRole("button", { name: "Supprimer model.api_key" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Supprimer" }));
    expect(await within(dialog).findByText(/sert encore à model\.api_key, triage_model\.api_key/)).toBeInTheDocument();
    expect("model.api_key" in db.config.vault).toBe(true);
    await user.click(within(dialog).getByRole("button", { name: "Supprimer quand même" }));
    await waitFor(() => expect("model.api_key" in db.config.vault).toBe(false));
  });

  it("is reserved to those who manage the configuration", async () => {
    const lea = db.accounts.find((a) => a.id === "acc-lea");
    if (lea) lea.role = "member";
    db.signedIn = "acc-lea";
    renderApp("/config/persona");
    expect(await screen.findByRole("heading", { name: "Section réservée" })).toBeInTheDocument();
  });
});
