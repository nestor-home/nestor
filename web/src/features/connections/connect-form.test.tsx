import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/i18n";
import { connectors } from "@/mocks/fixtures";
import { renderWithProviders } from "@/test/render";
import { ConnectForm } from "./connect-form";

const connector = (kind: string) => {
  const found = connectors().find((c) => c.kind === kind);
  if (!found) throw new Error(`no fixture ${kind}`);
  return found;
};

describe("connecting an account", () => {
  it("picks the owner by typing part of the name, then sends the browser to the consent page", async () => {
    const user = userEvent.setup();
    const leave = vi.fn();
    const onConnected = vi.fn();
    renderWithProviders(
      <I18nProvider>
        <ConnectForm connector={connector("google")} replaces={null} onConnected={onConnected} leave={leave} />
      </I18nProvider>,
    );
    const owner = screen.getByRole("combobox", { name: "Compte de" });
    await user.click(owner);
    await user.clear(owner);
    await user.type(owner, "léa");
    expect(await screen.findByRole("option", { name: "Léa" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Mathis" })).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(owner).toHaveValue("Léa"));

    await user.click(screen.getByRole("button", { name: "Connecter" }));
    expect(screen.getByRole("button", { name: "Connexion…" })).toBeDisabled();
    await waitFor(() =>
      expect(leave).toHaveBeenCalledWith(expect.stringMatching(/^\/connections\/c-.+\?connected=1$/)),
    );
    expect(screen.getByRole("button", { name: "Redirection vers le service…" })).toBeDisabled();
    expect(onConnected).not.toHaveBeenCalled();
  });

  it("cannot start OAuth before the household's client exists", () => {
    renderWithProviders(
      <I18nProvider>
        <ConnectForm connector={connector("google-calendar")} replaces={null} onConnected={vi.fn()} leave={vi.fn()} />
      </I18nProvider>,
    );
    expect(screen.getByRole("button", { name: "Connecter" })).toBeDisabled();
    expect(screen.getByText("Enregistrez d'abord le client OAuth du foyer.")).toBeInTheDocument();
  });

  it("connects a secret-based service at once, with trimmed values", async () => {
    const user = userEvent.setup();
    const onConnected = vi.fn();
    renderWithProviders(
      <I18nProvider>
        <ConnectForm connector={connector("imap")} replaces={null} onConnected={onConnected} />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText("Serveur IMAP"), "imap.fastmail.com ");
    await user.type(screen.getByLabelText("Identifiant"), "lea@lambert.family ");
    await user.type(screen.getByLabelText("Mot de passe d'application"), "s3cret-app");
    await user.click(screen.getByRole("button", { name: "Connecter" }));
    await waitFor(() =>
      expect(onConnected).toHaveBeenCalledWith(expect.objectContaining({ account: "lea@lambert.family" })),
    );
  });

  it("shows the provider's refusal and lets the person try again", async () => {
    const user = userEvent.setup();
    const onConnected = vi.fn();
    renderWithProviders(
      <I18nProvider>
        <ConnectForm connector={connector("imap")} replaces={null} onConnected={onConnected} />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText("Serveur IMAP"), "imap.invalide.example");
    await user.type(screen.getByLabelText("Identifiant"), "lea");
    await user.type(screen.getByLabelText("Mot de passe d'application"), "faux");
    await user.click(screen.getByRole("button", { name: "Connecter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le service a refusé la connexion");
    expect(screen.getByRole("button", { name: "Connecter" })).toBeEnabled();
    expect(onConnected).not.toHaveBeenCalled();
  });
});
