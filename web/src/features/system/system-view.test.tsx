import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { SCOPES } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

afterEach(() => server.events.removeAllListeners());

const part = (name: RegExp) => screen.findByRole("region", { name });

describe("the system page", () => {
  it("puts what is wrong first, with what to do about it", async () => {
    const unwell = db.system.components.filter((c) => c.health !== "started").length;
    renderApp("/system");
    expect(await screen.findByText(`${unwell} components to watch`)).toBeVisible();
    const wrong = await part(/^To look at/);
    expect(within(wrong).getAllByRole("button")).toHaveLength(unwell);
    const down = within(wrong).getByRole("button", { name: /^recipes/ });
    expect(down).toHaveTextContent("down");
    expect(down).toHaveTextContent("Connection refused by 192.168.1.20:8808");
    expect(down).toHaveTextContent("Check that the service behind it answers");
    expect(within(wrong).getByRole("button", { name: /google/ })).toHaveTextContent("1 account to authorise again");
  });

  it("says all is well when every component answers", async () => {
    for (const c of db.system.components) c.health = "started";
    renderApp("/system");
    expect(await screen.findByText("all is well")).toBeVisible();
    expect(screen.queryByRole("region", { name: /^To look at/ })).not.toBeInTheDocument();
  });

  it("groups the components by what they are, the voice models apart from the others", async () => {
    renderApp("/system");
    const voice = await part(/^Voice/);
    const models = await part(/^Models/);
    const spoken = db.system.components.filter((c) => c.model_type === "transcription" || c.model_type === "speech");
    expect(spoken.length).toBeGreaterThan(0);
    for (const c of spoken) {
      expect(within(voice).getByRole("button", { name: new RegExp(c.name) })).toBeVisible();
      expect(within(models).queryByRole("button", { name: new RegExp(`^${c.name}`) })).not.toBeInTheDocument();
    }
    expect(within(models).getByRole("button", { name: /sonnet/ })).toBeVisible();
  });

  it("names the model that answers when another fails", async () => {
    const sonnet = db.system.components.find((c) => c.name === "sonnet");
    if (!sonnet) throw new Error("the sonnet model is in the mocks");
    sonnet.fallback = "haiku";
    renderApp("/system");
    expect(await screen.findByText("fallback: haiku")).toBeInTheDocument();
  });

  it("opens a component in place, with what it tells about itself and the way to its settings", async () => {
    const user = userEvent.setup();
    renderApp("/system");
    const tools = await part(/^Tools/);
    await user.click(within(tools).getByRole("button", { name: /^recipes/ }));
    const sheet = await screen.findByRole("dialog", { name: "recipes" });
    expect(within(sheet).getByText("mcp", { selector: "dd" })).toBeVisible();
    expect(within(sheet).getByText(/Nothing goes through it for now/)).toBeVisible();
    expect(within(sheet).getByRole("link", { name: "Configure" })).toHaveAttribute("href", "/config/tools");
    expect(within(sheet).getByRole("link", { name: "Documentation" })).toHaveAttribute(
      "href",
      "https://nestorhome.dev/docs/tools/#a-server-in-the-configuration",
    );
  });

  it("restarts only once confirmed, then waits for the instance", async () => {
    const sent: string[] = [];
    server.events.on("request:start", ({ request }) => {
      if (request.method === "POST" && request.url.endsWith("/system/restart")) sent.push(request.url);
    });
    const user = userEvent.setup();
    renderApp("/system");
    await user.click(await screen.findByRole("button", { name: "Restart…" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Restart Richie?" });
    expect(within(confirm).getByText(/everyone signs in again/)).toBeVisible();
    expect(sent).toHaveLength(0);
    await user.click(within(confirm).getByRole("button", { name: "Restart now" }));
    expect(await screen.findByText("Restarting, back in a moment.")).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(sent).toHaveLength(1);
  });

  it("offers no restart to who does not manage the configuration", async () => {
    const admin = SCOPES.admin;
    SCOPES.admin = admin.filter((scope) => scope !== "config.manage");
    db.signedIn = "acc-lea";
    try {
      renderApp("/system");
      expect(await part(/^This instance/)).toBeVisible();
      expect(screen.queryByRole("button", { name: "Restart…" })).not.toBeInTheDocument();
    } finally {
      SCOPES.admin = admin;
    }
  });
});
