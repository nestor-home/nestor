import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { connectors } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderApp, renderWithProviders } from "@/test/render";
import { ConnectForm } from "./connect-form";

const connector = (kind: string) => {
  const found = connectors().find((c) => c.kind === kind);
  if (!found) throw new Error(`no fixture ${kind}`);
  return found;
};

describe("connecting an account", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("picks the owner by typing part of the name, then sends the browser to the consent page", async () => {
    // the browser leaves the admin for the provider: jsdom cannot navigate, so watch where it would go
    const assign = vi.fn();
    vi.stubGlobal("location", { origin: window.location.origin, href: window.location.href, assign });
    const authorizations: string[] = [];
    server.events.on("response:mocked", async ({ request, response }) => {
      if (request.url.endsWith("/connectors/google/authorizations"))
        authorizations.push(((await response.clone().json()) as { authorize_url: string }).authorize_url);
    });
    const user = userEvent.setup();
    renderApp("/connections/catalogue?connect=google");
    const sheet = await screen.findByRole("dialog", { name: "Gmail" });
    const owner = within(sheet).getByRole("combobox", { name: "Account of" });
    await user.click(owner);
    await user.clear(owner);
    await user.type(owner, "léa");
    expect(await screen.findByRole("option", { name: "Léa" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Mathis" })).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(owner).toHaveValue("Léa"));

    // hold the server's answer to see the form while it waits, then let it through
    let release = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post("/api/v1/connectors/:kind/authorizations", async () => {
        await held;
      }),
    );
    await user.click(within(sheet).getByRole("button", { name: "Connect" }));
    expect(await within(sheet).findByRole("button", { name: "Connecting…" })).toBeDisabled();
    expect(assign).not.toHaveBeenCalled();
    release();
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    expect(authorizations).toHaveLength(1);
    expect(assign).toHaveBeenCalledWith(authorizations[0]);
    expect(within(sheet).getByRole("button", { name: "Redirecting to the service…" })).toBeDisabled();
  });

  it("cannot start OAuth before the household's client exists", async () => {
    await renderWithProviders(
      <ConnectForm connector={connector("google-calendar")} replaces={null} onConnected={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Connect" })).toBeDisabled();
    expect(screen.getByText("Register the OAuth client first.")).toBeInTheDocument();
  });

  it("connects a secret-based service at once, with trimmed values", async () => {
    const user = userEvent.setup();
    const onConnected = vi.fn();
    await renderWithProviders(<ConnectForm connector={connector("imap")} replaces={null} onConnected={onConnected} />);
    await user.type(screen.getByLabelText("IMAP server"), "imap.example.org ");
    await user.type(screen.getByLabelText("Username"), "lea@lambert.family ");
    await user.type(screen.getByLabelText("App password"), "s3cret-app");
    await user.click(screen.getByRole("button", { name: "Connect" }));
    await waitFor(() =>
      expect(onConnected).toHaveBeenCalledWith(expect.objectContaining({ account: "lea@lambert.family" })),
    );
  });

  it("shows the provider's refusal and lets the person try again", async () => {
    const user = userEvent.setup();
    const onConnected = vi.fn();
    await renderWithProviders(<ConnectForm connector={connector("imap")} replaces={null} onConnected={onConnected} />);
    await user.type(screen.getByLabelText("IMAP server"), "imap.invalid.example");
    await user.type(screen.getByLabelText("Username"), "lea");
    await user.type(screen.getByLabelText("App password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The service refused the connection");
    expect(screen.getByRole("button", { name: "Connect" })).toBeEnabled();
    expect(onConnected).not.toHaveBeenCalled();
  });
});
