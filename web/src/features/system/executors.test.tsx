import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

async function executorRow(name: string): Promise<HTMLElement> {
  const section = await screen.findByRole("region", { name: /Nestor's tools for executors/ });
  const label = await within(section).findByText(name, { selector: "p" });
  const row = label.closest("li");
  if (!row) throw new Error(`${name} is a row`);
  return row;
}

describe("the executors' keys for Nestor's MCP server", () => {
  it("says how each executor reaches Nestor and when its key was made and used", async () => {
    renderApp("/system");
    expect(await screen.findByText(/executors reach Nestor at https:\/\/nestor.martin.family\/mcp/)).toBeVisible();
    const hermes = await executorRow("hermes");
    expect(within(hermes).getByText("Its own configuration declares Nestor's tools")).toBeVisible();
    expect(within(hermes).getByText(/Key made/)).toBeVisible();
    const claude = await executorRow("claude-code");
    expect(within(claude).getByText("No key")).toBeVisible();
  });

  it("shows a new key once, with what to paste in an executor configured by hand", async () => {
    const user = userEvent.setup();
    renderApp("/system");
    await user.click(within(await executorRow("hermes")).getByRole("button", { name: "Renew" }));
    const confirm = await screen.findByRole("alertdialog", { name: "Renew the key of hermes?" });
    expect(within(confirm).getByText(/The current key stops working at once/)).toBeVisible();
    await user.click(within(confirm).getByRole("button", { name: "Renew" }));
    const shown = await screen.findByRole("dialog", { name: "The key of hermes" });
    const key = within(shown).getByTitle(/^nstx_/).textContent ?? "";
    expect(within(shown).getByText(/mcp_servers:/)).toHaveTextContent(`Authorization: "Bearer ${key}"`);
    const [, done] = within(shown).getAllByRole("button", { name: "Close" }); // the dialog's cross, then its own
    if (!done) throw new Error("the dialog closes from its own button");
    await user.click(done);
    expect(screen.queryByText(key)).not.toBeInTheDocument();
  });

  it("needs nothing pasted for an executor Nestor launches", async () => {
    const user = userEvent.setup();
    renderApp("/system");
    await user.click(within(await executorRow("claude-code")).getByRole("button", { name: "Make a key" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Make a key" }));
    const shown = await screen.findByRole("dialog", { name: "The key of claude-code" });
    expect(within(shown).getByText(/nothing to paste/)).toBeVisible();
    expect(within(shown).queryByText(/mcp_servers:/)).not.toBeInTheDocument();
  });

  it("revokes a key", async () => {
    const user = userEvent.setup();
    renderApp("/system");
    await user.click(within(await executorRow("codex")).getByRole("button", { name: "Revoke" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Revoke" }));
    expect(await within(await executorRow("codex")).findByText("No key")).toBeVisible();
  });

  it("says what is missing when executors cannot reach Nestor", async () => {
    db.executors.url = null;
    renderApp("/system");
    expect(await screen.findByText(/give the admin a public_url/)).toBeVisible();
    expect(within(await executorRow("hermes")).queryByRole("button")).not.toBeInTheDocument();
  });

  it("says when the executors could not be read, and tries again", async () => {
    server.use(http.get("/api/v1/executors", () => HttpResponse.json({}, { status: 500 }), { once: true }));
    const user = userEvent.setup();
    renderApp("/system");
    const section = await screen.findByRole("region", { name: /Nestor's tools for executors/ });
    await user.click(await within(section).findByRole("button", { name: /Try again/ }));
    expect(await executorRow("hermes")).toBeVisible();
  });
});
