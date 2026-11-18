import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { components } from "@/api/schema.gen";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

type ErrorOut = components["schemas"]["ErrorOut"];

describe("a task's page", () => {
  it("tells a task from its request to its delivery", async () => {
    renderApp("/tasks/t-3f2a1c");
    expect(
      await screen.findByRole("heading", { name: /Compare three green electricity offers/, level: 1 }),
    ).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumbs" });
    expect(within(crumbs).getByRole("link", { name: "Ongoing" })).toHaveAttribute("href", "/activity");
    expect(screen.getByRole("region", { name: "Result" })).toHaveTextContent("The second offer is the cheapest");
    const steps = within(screen.getByRole("region", { name: /^Steps/ })).getAllByRole("listitem");
    expect(steps.map((s) => s.textContent)).toEqual([
      "Read the last two bills.",
      "Price lists of the three suppliers fetched.",
      "Worked out over a year, standing charge included.",
    ]);
    const about = screen.getByRole("complementary", { name: "About this task" });
    expect(about).toHaveTextContent("Mathis");
    expect(about).toHaveTextContent(/Said out loud, in the office/);
    expect(within(about).getByRole("link", { name: /a conversation/ })).toHaveAttribute(
      "href",
      "/journal?session=s-elec",
    );
    const chain = await screen.findByRole("article");
    for (const step of ["started", "completed", "decision", "said out loud"])
      expect(within(chain).getByText(step)).toBeInTheDocument();
  });

  it("hands over the files a task made, with its result and in its story", async () => {
    const pdf = {
      index: 0,
      name: "devis-corrige.pdf",
      kind: "file",
      media_type: "application/pdf",
      size: 2048,
    } as const;
    const task = db.tasks.find((t) => t.id === "t-3f2a1c");
    const ended = db.journal.find((e) => e.record.type === "task.ended" && e.item.links.task === "t-3f2a1c");
    if (!task || !ended) throw new Error("the energy task is in the mocks");
    task.files = [pdf];
    ended.item.attachments = [{ ...pdf, transcript: null }];
    renderApp("/tasks/t-3f2a1c");
    const chain = await screen.findByRole("article");
    expect(within(chain).getByRole("link", { name: /devis-corrige\.pdf/ })).toHaveAttribute(
      "href",
      `/api/v1/journal/${ended.item.position}/attachments/0`,
    );
    const result = screen.getByRole("region", { name: "Result" });
    expect(within(result).getByRole("link", { name: /devis-corrige\.pdf/ })).toHaveAttribute(
      "href",
      "/api/v1/tasks/t-3f2a1c/files/0",
    );
  });

  it("leads a running task with what it is doing now", async () => {
    renderApp("/tasks/t-4410aa");
    const now = await screen.findByRole("region", { name: "Right now" });
    expect(now).toHaveTextContent("Waiting for the invoice: Gmail needs reconnecting.");
    expect(now).toHaveTextContent("The result will reach the person wherever they are.");
    expect(screen.queryByRole("region", { name: "Result" })).not.toBeInTheDocument();
  });

  it("says why a failed task gave nothing", async () => {
    renderApp("/tasks/t-a04f12");
    expect(await screen.findByRole("region", { name: "What went wrong" })).toHaveTextContent(
      "The site asks for a sign-in by text message",
    );
    expect(screen.queryByRole("button", { name: "Stop…" })).not.toBeInTheDocument();
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
});
