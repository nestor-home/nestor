import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { components } from "@/api/schema.gen";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

type ErrorOut = components["schemas"]["ErrorOut"];

describe("tasks and watches", () => {
  it("tells a task from its request to its delivery", async () => {
    renderApp("/tasks/t-3f2a1c");
    expect(
      await screen.findByRole("heading", { name: /Compare three green electricity offers/, level: 1 }),
    ).toBeInTheDocument();
    const chain = await screen.findByRole("article");
    for (const step of ["started", "completed", "decision", "said out loud"])
      expect(within(chain).getByText(step)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /a conversation/ })).toHaveAttribute("href", "/journal?session=s-elec");
  });

  it("stops a running task once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/tasks/t-4410aa");
    await user.click(await screen.findByRole("button", { name: "Stop…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(db.tasks.find((t) => t.id === "t-4410aa")?.status).toBe("cancelled"));
  });

  it("keeps the dialog open with the reason when stopping fails", async () => {
    server.use(
      http.post("/api/v1/tasks/:id/cancel", () =>
        HttpResponse.json(
          {
            // a provider's failure, as Nestor answers it (`ProviderError` → `provider_error`)
            error: {
              code: "provider_error",
              message_id: "error-provider-error",
              args: { detail: "the executor does not answer" },
              message: "The service is not responding: the executor does not answer.",
            },
          } satisfies ErrorOut,
          { status: 502 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderApp("/tasks/t-4410aa");
    await user.click(await screen.findByRole("button", { name: "Stop…" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Stop" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "The service is not responding: the executor does not answer.",
    );
  });

  it("offers to retry when Nestor is unreachable", async () => {
    server.use(http.get("/api/v1/tasks", () => HttpResponse.error()));
    const user = userEvent.setup();
    renderApp("/tasks");
    expect(await screen.findByRole("alert")).toHaveTextContent("Nestor does not answer");
    server.resetHandlers();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/Make the week's shopping list/)).toBeInTheDocument();
  });

  it("tells what a watch found and how it was announced", async () => {
    renderApp("/watches/w-9d41");
    const articles = await screen.findAllByRole("article");
    const chain = articles.find((a) => a.textContent?.includes("triggered")) as HTMLElement;
    // the conversation where Léa answered is linked to the watch too, as its own thread
    expect(articles.some((a) => a.textContent?.includes("Put it in the family calendar"))).toBe(true);
    expect(chain).toHaveTextContent("why: Léa is in the living room");
    expect(chain).toHaveTextContent("follow-up");
  });

  it("points to the catalogue when no source can feed a watch", async () => {
    db.watches = [];
    db.connectors = db.connectors.map((c) => ({ ...c, inbound: [] }));
    renderApp("/watches");
    expect(await screen.findByText("No active watch.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "connect a mailbox" })).toHaveAttribute("href", "/connections/catalogue");
  });
});
