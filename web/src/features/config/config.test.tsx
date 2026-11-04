import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";
import { markOf } from "./config-pages";

const saveBar = () => screen.findByRole("region", { name: "Unsaved changes" });

describe("the configuration", () => {
  it("renders every kind of setting with its control", async () => {
    const user = userEvent.setup();
    renderApp("/config/tools");
    await user.click(await screen.findByRole("button", { name: "Edit home" }));
    const sheet = await screen.findByRole("dialog", { name: "home" });
    expect(within(sheet).getByRole("textbox", { name: "Address" })).toHaveValue(
      "http://homeassistant.local:8123/mcp_server/sse",
    );
    expect(within(sheet).getByRole("combobox", { name: "Transport" })).toHaveTextContent("sse");
    expect(within(sheet).getByText(`reference \${secret:tools.home.token}`)).toBeInTheDocument();
    const timeout = within(sheet).getByRole("spinbutton", { name: "Timeout (seconds)" });
    expect(timeout).toHaveAttribute("placeholder", "10");
    expect(timeout).toHaveAttribute("min", "0");
    expect(within(sheet).getByRole("textbox", { name: "Tool risks, name 1" })).toHaveValue("HassTurnOff");
  });

  it("keeps a secret unless it is replaced, and never shows its value", async () => {
    const user = userEvent.setup();
    renderApp("/config/presence");
    const panel = (await screen.findAllByText(`reference \${secret:presence.token}`))[0];
    expect(panel).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Replace Token" })[0] as HTMLElement);
    const field = screen.getAllByLabelText("Token")[0] as HTMLInputElement;
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveValue("");
    await user.type(field, "eyJhbGciOiJIUzI1NiJ9.new");
    await user.click(await screen.findByRole("button", { name: "1 change" }));
    const changes = await screen.findByRole("dialog", { name: "Changes" });
    expect(within(changes).getByText("presence.token")).toBeInTheDocument();
    expect(within(changes).getByText("secret changed")).toBeInTheDocument();
    expect(changes).not.toHaveTextContent("eyJhbGciOiJIUzI1NiJ9.new");
    await user.keyboard("{Escape}");
    await user.click(screen.getAllByRole("button", { name: "Keep current" })[0] as HTMLElement);
    await waitFor(() => expect(screen.queryByRole("region", { name: "Unsaved changes" })).not.toBeInTheDocument());
  });

  it("names the models, and renaming one keeps the roles that use it", async () => {
    const user = userEvent.setup();
    renderApp("/config/models");
    expect(await screen.findByRole("combobox", { name: "Spoken model" })).toHaveTextContent("haiku");
    await user.click(screen.getByRole("button", { name: "Edit haiku" }));
    const sheet = await screen.findByRole("dialog", { name: "haiku" });
    const name = within(sheet).getByRole("textbox", { name: "Name" });
    await user.clear(name);
    await user.type(name, "sonnet");
    expect(within(sheet).getByText("This name is already taken.")).toBeInTheDocument();
    await user.clear(name);
    await user.type(name, "fast{Enter}");
    await user.click(within(sheet).getByRole("button", { name: "Done" }));
    expect(screen.getByRole("button", { name: "Edit fast" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Spoken model" })).toHaveTextContent("fast");
    expect(screen.getByRole("combobox", { name: "Sorting model" })).toHaveTextContent("fast");
    expect(screen.getByRole("combobox", { name: "Written model" })).toHaveTextContent("sonnet");
  });

  it("folds the advanced settings until asked", async () => {
    const user = userEvent.setup();
    renderApp("/config/initiative");
    expect(await screen.findByLabelText("Quiet hours")).toHaveValue("22:30-07:30");
    expect(screen.queryByLabelText("Written follow-up after (seconds)")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Advanced · 1 setting" }));
    expect(screen.getByLabelText("Written follow-up after (seconds)")).toBeVisible();
  });

  it("adds to and removes from a list", async () => {
    const user = userEvent.setup();
    renderApp("/config/household");
    await user.click(await screen.findByRole("button", { name: "Edit Jules" }));
    const sheet = await screen.findByRole("dialog", { name: "Jules" });
    await user.click(within(sheet).getByRole("button", { name: "Add" }));
    await user.type(within(sheet).getByRole("textbox", { name: "Accounts on channels, item 2" }), "telegram:@jules");
    await user.click(within(sheet).getByRole("button", { name: "Done" }));
    await user.click(await screen.findByRole("button", { name: "1 change" }));
    const changes = await screen.findByRole("dialog", { name: "Changes" });
    expect(within(changes).getByText("household.2.accounts.1")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: "Edit Jules" }));
    const again = await screen.findByRole("dialog", { name: "Jules" });
    await user.click(within(again).getByRole("button", { name: "Remove telegram:@jules" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Unsaved changes" })).not.toBeInTheDocument());
  });

  it("shows a problem at its field, and on the page that holds it", async () => {
    const user = userEvent.setup();
    renderApp("/config/channels");
    await user.click(await screen.findByRole("button", { name: "Edit Satellites" }));
    const sheet = await screen.findByRole("dialog", { name: "Satellites" });
    await user.clear(within(sheet).getByRole("spinbutton", { name: "Port" }));
    await user.type(within(sheet).getByRole("spinbutton", { name: "Port" }), "70000");
    expect(await within(sheet).findByText("Port: ≤ 65535")).toBeInTheDocument();
    expect(within(sheet).getByRole("spinbutton", { name: "Port" })).toHaveAttribute("aria-invalid", "true");
    await user.click(within(sheet).getByRole("button", { name: "Done" }));
    expect(within(await saveBar()).getByRole("button", { name: "1 problem" })).toBeInTheDocument();
    expect(within(await saveBar()).getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("link", { name: /Channels\s*1/ })).toBeInTheDocument();
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
              message: "The configuration cannot be used (one problem): nothing was written.",
              problems: [
                {
                  path: ["persona", "timezone"],
                  code: "invalid",
                  message_id: "config-error-invalid",
                  args: { path: "persona.timezone", detail: "unknown time zone" },
                  message: "persona.timezone: unknown time zone",
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
    const zone = await screen.findByRole("textbox", { name: "Time zone" });
    await user.clear(zone);
    await user.type(zone, "Mars/Olympus");
    const bar = await saveBar();
    await waitFor(() => expect(within(bar).getByRole("button", { name: "Save" })).toBeEnabled());
    await user.click(within(bar).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Time zone: unknown time zone")).toBeInTheDocument();
    expect(db.config.restart_required).toBe(false);
  });

  it("saves, then asks for a restart that a person starts, and reconnects", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/config/persona");
    const name = await screen.findByRole("textbox", { name: "Name" });
    await user.clear(name);
    await user.type(name, "Alfred");
    const bar = await saveBar();
    await waitFor(() => expect(within(bar).getByRole("button", { name: "Save" })).toBeEnabled());
    await user.click(within(bar).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Restart required")).toBeInTheDocument();
    expect(screen.getByText(/1 pending change/)).toBeInTheDocument();
    expect(db.config.restart_required).toBe(true);
    // nothing restarts by itself
    expect(screen.getByRole("link", { name: /Richie/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Restart…" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Restart Richie?" });
    expect(dialog).toHaveTextContent("Channels close");
    expect(dialog).toHaveTextContent("Remote tasks keep running");
    await user.click(within(dialog).getByRole("button", { name: "Restart now" }));
    expect(await screen.findByText("Restarting, back in a moment.")).toBeInTheDocument();
    // sessions live in the process's memory: the restarted instance asks to sign in again, then comes back
    expect(await screen.findByText(/I'm back, configuration applied/, {}, { timeout: 8_000 })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ next: "/config/persona" });
    await user.type(screen.getByLabelText("Login"), "mathis");
    await user.type(screen.getByLabelText("Password"), "nestor");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("link", { name: /Alfred/ })).toBeInTheDocument();
    expect(screen.queryByText("Restart required")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/config/persona");
  }, 20_000);

  it("explains why a secret in use is not deleted, and deletes it only when insisted", async () => {
    const user = userEvent.setup();
    renderApp("/config/secrets");
    await user.click(await screen.findByRole("button", { name: "Delete presence.token" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await within(dialog).findByText(/still used by presence\.token/)).toBeInTheDocument();
    expect("presence.token" in db.config.vault).toBe(true);
    await user.click(within(dialog).getByRole("button", { name: "Delete anyway" }));
    await waitFor(() => expect("presence.token" in db.config.vault).toBe(false));
  });

  it("is reserved to those who manage the configuration", async () => {
    const lea = db.accounts.find((a) => a.id === "acc-lea");
    if (lea) lea.role = "member";
    db.signedIn = "acc-lea";
    renderApp("/config/persona");
    expect(await screen.findByRole("heading", { name: "Restricted section" })).toBeInTheDocument();
  });

  it("keeps or replaces each secret of a map on its own (MCP headers)", async () => {
    const user = userEvent.setup();
    renderApp("/config/tools");
    await user.click(await screen.findByRole("button", { name: "Edit home" }));
    const sheet = await screen.findByRole("dialog", { name: "home" });
    expect(within(sheet).getByText(/set · lam•••2f/)).toBeInTheDocument();
    expect(sheet).not.toHaveTextContent("lambert-home-7d2f");
    await user.click(within(sheet).getByRole("button", { name: /Replace HTTP headers, value of X-Household/ }));
    await user.type(within(sheet).getByLabelText("HTTP headers, value of X-Household"), "new-household-key");
    await user.click(within(sheet).getByRole("button", { name: "Done" }));
    await user.click(await screen.findByRole("button", { name: "1 change" }));
    const changes = await screen.findByRole("dialog", { name: "Changes" });
    expect(within(changes).getByText("tools.0.headers.X-Household")).toBeInTheDocument();
    expect(within(changes).getByText("secret changed")).toBeInTheDocument();
  });

  it("shows any section the schema has, such as when a conversation ends", async () => {
    renderApp("/config/conversation");
    expect(await screen.findByRole("heading", { name: "Conversations" })).toBeInTheDocument();
    const field = await screen.findByRole("spinbutton", { name: "New conversation after (seconds)" });
    expect(field).toHaveAttribute("placeholder", "300");
    expect(screen.getByText(/starts a new conversation/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Conversations/ })).toHaveAttribute("href", "/config/conversation");
  });
});

describe("a model's mark", () => {
  const schema = {
    properties: { base_url: { "x-brands": { "openrouter.ai": "openrouter", "anthropic.com": "anthropic" } } },
  };

  it("is the provider its address belongs to, as the runtime recognises it", () => {
    expect(markOf("openai-compatible", { base_url: "https://openrouter.ai/api/v1" }, schema)).toBe("openrouter");
    expect(markOf("openai-compatible", { base_url: "https://api.anthropic.com/v1" }, schema)).toBe("anthropic");
  });

  it("is its kind for any other server, an address still to write, or a kind that publishes no hosts", () => {
    expect(markOf("openai-compatible", { base_url: "http://localhost:11434/v1" }, schema)).toBe("openai-compatible");
    expect(markOf("openai-compatible", { base_url: "${MODEL_URL}" }, schema)).toBe("openai-compatible");
    expect(markOf("hermes", { base_url: "https://openrouter.ai" }, {})).toBe("hermes");
  });
});
