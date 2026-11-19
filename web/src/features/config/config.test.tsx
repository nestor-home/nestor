import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { RESTART_MS } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";
import { RESTART_POLL_MS } from "./restart";
import { markOf } from "./summary";

const saveBar = () => screen.findByRole("region", { name: "Unsaved changes" });

describe("the configuration", () => {
  it("renders every kind of setting with its control", async () => {
    const user = userEvent.setup();
    renderApp("/config/tools");
    await user.click(await screen.findByRole("button", { name: /^recipes/ }));
    const sheet = await screen.findByRole("dialog", { name: "recipes" });
    expect(within(sheet).getByRole("textbox", { name: "URL" })).toHaveValue("http://192.168.1.20:8808/mcp_server/sse");
    expect(within(sheet).getByRole("combobox", { name: "Transport" })).toHaveTextContent("sse");
    expect(within(sheet).getByText(`reference \${secret:tools.recipes.token}`)).toBeInTheDocument();
    const timeout = within(sheet).getByRole("spinbutton", { name: "Timeout (seconds)" });
    expect(timeout).toHaveAttribute("placeholder", "10");
    expect(timeout).toHaveAttribute("min", "0");
    expect(within(sheet).getByRole("textbox", { name: "Tool risks, name 1" })).toHaveValue("add_recipe");
    // the kind picks the plugin: it is never a setting
    expect(within(sheet).queryByText("Kind")).not.toBeInTheDocument();
  });

  it("keeps a secret unless it is replaced, and never shows its value", async () => {
    const user = userEvent.setup();
    renderApp("/config/home");
    await user.click(await screen.findByRole("button", { name: /^Home Assistant/ }));
    const sheet = await screen.findByRole("dialog", { name: "Home Assistant" });
    expect(within(sheet).getByText(`reference \${secret:home.token}`)).toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Replace Token" }));
    const field = within(sheet).getByLabelText("Token");
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveValue("");
    await user.type(field, "eyJhbGciOiJIUzI1NiJ9.new");
    await user.click(within(sheet).getByRole("button", { name: "Done" }));
    await user.click(await screen.findByRole("button", { name: "1 change" }));
    const changes = await screen.findByRole("dialog", { name: "Changes" });
    expect(within(changes).getByText("home.token")).toBeInTheDocument();
    expect(within(changes).getByText("secret changed")).toBeInTheDocument();
    expect(changes).not.toHaveTextContent("eyJhbGciOiJIUzI1NiJ9.new");
    await user.keyboard("{Escape}");
    expect(document.body).not.toHaveTextContent("eyJhbGciOiJIUzI1NiJ9.new");
    await user.click(screen.getByRole("button", { name: /^Home Assistant/ }));
    await user.click(await screen.findByRole("button", { name: "Keep current" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Unsaved changes" })).not.toBeInTheDocument());
  });

  it("names the models, and renaming one keeps the roles that use it", async () => {
    const user = userEvent.setup();
    renderApp("/config/models");
    // a model's card says which roles it serves
    expect(await screen.findByRole("button", { name: /^haiku.*Spoken model.*Sorting model/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^haiku/ }));
    const sheet = await screen.findByRole("dialog", { name: "haiku" });
    const name = within(sheet).getByRole("textbox", { name: "Name" });
    await user.clear(name);
    await user.type(name, "sonnet");
    expect(within(sheet).getByText("This name is already taken.")).toBeInTheDocument();
    await user.clear(name);
    await user.type(name, "fast{Enter}");
    await user.click(within(sheet).getByRole("button", { name: "Done" }));
    expect(screen.getByRole("button", { name: /^fast.*Spoken model.*Sorting model/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^sonnet.*Written model/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit Agent" }));
    const roles = await screen.findByRole("dialog", { name: "Agent" });
    expect(within(roles).getByRole("combobox", { name: "Spoken model" })).toHaveTextContent("fast");
    expect(within(roles).getByRole("combobox", { name: "Written model" })).toHaveTextContent("sonnet");
  });

  it("folds the advanced settings until asked", async () => {
    const user = userEvent.setup();
    renderApp("/config/initiative");
    // the page says what is set; its form opens on demand
    expect(await screen.findByText("22:30-07:30")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit Initiative" }));
    expect(await screen.findByLabelText("Quiet hours")).toHaveValue("22:30-07:30");
    expect(screen.queryByLabelText("Written follow-up after (seconds)")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Advanced · 1 setting" }));
    expect(screen.getByLabelText("Written follow-up after (seconds)")).toBeVisible();
  });

  it("adds to and removes from a list", async () => {
    const user = userEvent.setup();
    renderApp("/config/household");
    await user.click(await screen.findByRole("button", { name: /^Jules/ }));
    const sheet = await screen.findByRole("dialog", { name: "Jules" });
    await user.click(within(sheet).getByRole("button", { name: "Add to Accounts" }));
    await user.type(within(sheet).getByRole("textbox", { name: "Accounts, item 2" }), "telegram:@jules");
    await user.click(within(sheet).getByRole("button", { name: "Done" }));
    await user.click(await screen.findByRole("button", { name: "1 change" }));
    const changes = await screen.findByRole("dialog", { name: "Changes" });
    expect(within(changes).getByText("household.2.accounts.1")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: /^Jules.*telegram:@jules/ }));
    const again = await screen.findByRole("dialog", { name: "Jules" });
    await user.click(within(again).getByRole("button", { name: "Remove telegram:@jules" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Unsaved changes" })).not.toBeInTheDocument());
  });

  it("shows a problem at its field, and on the page that holds it", async () => {
    const user = userEvent.setup();
    renderApp("/config/channels");
    await user.click(await screen.findByRole("button", { name: /^Satellites/ }));
    const sheet = await screen.findByRole("dialog", { name: "Satellites" });
    await user.clear(within(sheet).getByRole("spinbutton", { name: "Port" }));
    await user.type(within(sheet).getByRole("spinbutton", { name: "Port" }), "70000");
    expect(await within(sheet).findByText("Port: ≤ 65535")).toBeInTheDocument();
    expect(within(sheet).getByRole("spinbutton", { name: "Port" })).toHaveAttribute("aria-invalid", "true");
    await user.click(within(sheet).getByRole("button", { name: "Done" }));
    expect(within(await saveBar()).getByRole("button", { name: "1 problem" })).toBeInTheDocument();
    expect(within(await saveBar()).getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Satellites.*1 problem/ })).toBeInTheDocument();
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
    await user.click(await screen.findByRole("button", { name: "Edit Persona" }));
    const zone = await screen.findByRole("textbox", { name: "Time zone" });
    await user.clear(zone);
    await user.type(zone, "Mars/Olympus");
    await user.click(screen.getByRole("button", { name: "Done" }));
    const bar = await saveBar();
    await waitFor(() => expect(within(bar).getByRole("button", { name: "Save" })).toBeEnabled());
    await user.click(within(bar).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Time zone: unknown time zone")).toBeInTheDocument();
    expect(db.config.restart_required).toBe(false);
  });

  it("saves, then asks for a restart that a person starts, and reconnects", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/config/persona");
    await user.click(await screen.findByRole("button", { name: "Edit Persona" }));
    const name = await screen.findByRole("textbox", { name: "Name" });
    await user.clear(name);
    await user.type(name, "Alfred");
    await user.click(screen.getByRole("button", { name: "Done" }));
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
    expect(dialog).toHaveTextContent("Delegated tasks keep running");
    await user.click(within(dialog).getByRole("button", { name: "Restart now" }));
    expect(await screen.findByText("Restarting, back in a moment.")).toBeInTheDocument();
    // sessions live in the process's memory: the restarted instance asks to sign in again, then comes back. The
    // mock is down for real seconds, polled every second: a CI runner busy with other test files needs the slack
    const back = { timeout: RESTART_MS + RESTART_POLL_MS + 8_000 };
    expect(await screen.findByText(/I'm back, configuration applied/, {}, back)).toBeInTheDocument();
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
    await user.click(await screen.findByRole("button", { name: "Delete home.token" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(await within(dialog).findByText(/still used by home\.token/)).toBeInTheDocument();
    expect("home.token" in db.config.vault).toBe(true);
    await user.click(within(dialog).getByRole("button", { name: "Delete anyway" }));
    await waitFor(() => expect("home.token" in db.config.vault).toBe(false));
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
    await user.click(await screen.findByRole("button", { name: /^recipes/ }));
    const sheet = await screen.findByRole("dialog", { name: "recipes" });
    expect(within(sheet).getByText(/set · mar•••2f/)).toBeInTheDocument();
    expect(sheet).not.toHaveTextContent("martin-home-7d2f");
    await user.click(within(sheet).getByRole("button", { name: /Replace HTTP headers, value of X-Household/ }));
    await user.type(within(sheet).getByLabelText("HTTP headers, value of X-Household"), "new-household-key");
    await user.click(within(sheet).getByRole("button", { name: "Done" }));
    await user.click(await screen.findByRole("button", { name: "1 change" }));
    const changes = await screen.findByRole("dialog", { name: "Changes" });
    expect(within(changes).getByText("tools.0.headers.X-Household")).toBeInTheDocument();
    expect(within(changes).getByText("secret changed")).toBeInTheDocument();
  });

  it("shows any section the schema has, such as which memories each turn carries", async () => {
    renderApp("/config/memory");
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Memory" })).toBeInTheDocument();
    // what applies when the file says nothing is shown, not left blank
    expect(screen.getByText("Default (150)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Memory/ })).toHaveAttribute("href", "/config/memory");
    await user.click(screen.getByRole("button", { name: "Edit Memory" }));
    const field = await screen.findByRole("spinbutton", { name: "Latest memories per turn" });
    expect(field).toHaveAttribute("placeholder", "150");
  });
});

describe("the configuration at a glance", () => {
  it("says what each part holds now, by what one tunes", async () => {
    delete db.config.document.inbound; // a household that follows no feed, page or webhook
    renderApp("/config");
    const talk = await screen.findByRole("region", { name: "How it talks and listens" });
    expect(within(talk).getByRole("link", { name: /Models.*sonnet, haiku, voices and 2 more/ })).toHaveAttribute(
      "href",
      "/config/models",
    );
    expect(within(talk).getByRole("link", { name: /Channels.*Satellites, .*Telegram and 9 more/ })).toBeInTheDocument();
    const household = screen.getByRole("region", { name: "The household" });
    expect(within(household).getByRole("link", { name: /Household.*4 people/ })).toBeInTheDocument();
    const reach = screen.getByRole("region", { name: "What it can reach" });
    expect(within(reach).getByRole("link", { name: /Inbound sources.*Nothing set up/ })).toBeInTheDocument();
    const install = screen.getByRole("region", { name: "The installation" });
    expect(await within(install).findByRole("link", { name: /History.*2 earlier versions/ })).toBeInTheDocument();
  });

  it("states what is not saved yet first, with the part it touches", async () => {
    const user = userEvent.setup();
    renderApp("/config/persona");
    await user.click(await screen.findByRole("button", { name: "Edit Persona" }));
    const name = await screen.findByRole("textbox", { name: "Name" });
    await user.clear(name);
    await user.type(name, "Alfred");
    await user.click(screen.getByRole("button", { name: "Done" }));
    await user.click(
      within(screen.getByRole("navigation", { name: "Breadcrumbs" })).getByRole("link", { name: "Configuration" }),
    );
    const bar = await saveBar();
    expect(await within(bar).findByRole("button", { name: "1 change" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Persona.*Alfred.*modified/ })).toBeInTheDocument();
    await user.click(within(bar).getByRole("button", { name: "Discard changes" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Unsaved changes" })).not.toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Persona.*Richie/ })).toBeInTheDocument();
  });

  it("leads to any other part from a page, in a drawer on a narrow screen", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/config/persona");
    await user.click(await screen.findByRole("button", { name: "Sections" }));
    const drawer = await screen.findByRole("dialog", { name: "Configuration" });
    await user.click(within(drawer).getByRole("link", { name: "Secrets" }));
    expect(await screen.findByRole("heading", { name: "Secrets", level: 1 })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/config/secrets");
  });
});

describe("a component", () => {
  it("leaves the file only once confirmed, from its sheet", async () => {
    const user = userEvent.setup();
    renderApp("/config/tools");
    await user.click(await screen.findByRole("button", { name: /^recipes/ }));
    const sheet = await screen.findByRole("dialog", { name: "recipes" });
    await user.click(within(sheet).getByRole("button", { name: "Remove" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Remove recipes?" });
    expect(screen.getByRole("button", { name: /^recipes/, hidden: true })).toBeInTheDocument();
    await user.click(within(confirm).getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /^recipes/ })).not.toBeInTheDocument());
    await user.click(await within(await saveBar()).findByRole("button", { name: /\d+ changes?/ }));
    expect(await screen.findByRole("dialog", { name: "Changes" })).toHaveTextContent("tools");
  });

  it("is chosen by its logo, then filled in, and cancelling leaves nothing behind", async () => {
    const user = userEvent.setup();
    renderApp("/config/channels");
    await user.click(await screen.findByRole("button", { name: /^Add/ }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: /^Discord/ }));
    const sheet = await screen.findByRole("dialog", { name: "Add Discord" });
    await user.click(within(sheet).getByRole("button", { name: "Cancel adding" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Unsaved changes" })).not.toBeInTheDocument());
    // the household's own Discord channel, and no second one
    expect(screen.getAllByRole("button", { name: /^Discord/ })).toHaveLength(1);
  });

  it("is cancelled too when its sheet is dismissed before Done", async () => {
    const user = userEvent.setup();
    renderApp("/config/channels");
    await user.click(await screen.findByRole("button", { name: /^Add/ }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: /^Discord/ }));
    await screen.findByRole("dialog", { name: "Add Discord" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("region", { name: "Unsaved changes" })).not.toBeInTheDocument());
    // the household's own Discord channel, and no second one
    expect(screen.getAllByRole("button", { name: /^Discord/ })).toHaveLength(1);
  });
});

describe("the history", () => {
  it("opens an earlier version with what restoring it would change, and restores it once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/config/history");
    const versions = await within(await screen.findByRole("region", { name: /Earlier versions/ })).findAllByRole(
      "button",
    );
    await user.click(versions[0] as HTMLElement);
    const sheet = await screen.findByRole("dialog");
    expect(await within(sheet).findByText(/Restoring would change \d+ settings?\./)).toBeInTheDocument();
    expect(within(sheet).getByText("persona.character")).toBeInTheDocument();
    expect(db.config.restart_required).toBe(false);
    await user.click(within(sheet).getByRole("button", { name: "Restore" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Restore this version?" });
    await user.click(within(confirm).getByRole("button", { name: "Restore" }));
    expect(await screen.findByText("Restart required")).toBeInTheDocument();
    expect(db.config.restart_required).toBe(true);
  });
});

describe("models by what they serve", () => {
  it("are added by type, and a role is offered only the models of its type", async () => {
    const user = userEvent.setup();
    renderApp("/config/models");
    await user.click(await screen.findByRole("button", { name: /^Add/ }));
    const picker = await screen.findByRole("dialog");
    // the type first, each with its word; then who provides it
    const types = within(within(picker).getByRole("list", { name: "Type of model" }))
      .getAllByRole("button")
      .map((b) => b.textContent?.replace(/To .*/, ""));
    expect(types).toEqual(["Language", "Embeddings", "Speaker voice", "Transcription", "Speech", "Images"]);
    expect(within(picker).queryByText("sherpa-onnx")).not.toBeInTheDocument();
    await user.click(within(picker).getByRole("button", { name: /^Speaker voice/ }));
    expect(within(within(picker).getByRole("list", { name: "Speaker voice" })).getByText("sherpa-onnx")).toBeTruthy();
    await user.keyboard("{Escape}");

    // a model's card says its type beside its provider
    expect((await screen.findAllByText("Speaker voice")).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Edit Agent" }));
    await user.click(await screen.findByRole("combobox", { name: "Spoken model" }));
    const options = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(options).toContain("haiku");
    expect(options).not.toContain("ears");
  });
});

describe("a model's mark", () => {
  const schema = {
    properties: {
      base_url: { "x-nestor": { brands: { "openrouter.ai": "openrouter", "anthropic.com": "anthropic" } } },
    },
  };

  it("is the provider its address belongs to, as the runtime recognises it", () => {
    expect(markOf("openai-compatible", { base_url: "https://openrouter.ai/api/v1" }, schema)).toBe("openrouter");
    expect(markOf("openai-compatible", { base_url: "https://api.anthropic.com/v1" }, schema)).toBe("anthropic");
  });

  it("is the publisher of a catalogue model it names, else the runtime that runs it", () => {
    const voice = { properties: { model: { "x-nestor": { brands: { "titanet-small": "nvidia" } } } } };
    expect(markOf("sherpa-onnx", { model: "titanet-small" }, voice)).toBe("nvidia");
    expect(markOf("sherpa-onnx", { model: "/models/mine.onnx" }, voice)).toBe("sherpa-onnx");
  });

  it("is its kind for any other server, an address still to write, or a kind that publishes no hosts", () => {
    expect(markOf("openai-compatible", { base_url: "http://localhost:11434/v1" }, schema)).toBe("openai-compatible");
    // biome-ignore lint/suspicious/noTemplateCurlyInString: a configuration value still to be filled, as the file writes it
    expect(markOf("openai-compatible", { base_url: "${MODEL_URL}" }, schema)).toBe("openai-compatible");
    expect(markOf("hermes", { base_url: "https://openrouter.ai" }, {})).toBe("hermes");
  });
});
