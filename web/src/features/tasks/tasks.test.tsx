import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { components } from "@/api/schema.gen";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

type ErrorOut = components["schemas"]["ErrorOut"];

const task = (id: string) => {
  const found = db.tasks.find((t) => t.id === id);
  if (!found) throw new Error(`${id} is in the mocks`);
  return found;
};

describe("a task's page", () => {
  it("reads its thread like a conversation: each instruction, what came back, the files both ways, its notes", async () => {
    renderApp("/tasks/t-3f2a1c");
    expect(await screen.findByRole("heading", { name: "Green electricity offers", level: 1 })).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumbs" });
    expect(within(crumbs).getByRole("link", { name: "Ongoing" })).toHaveAttribute("href", "/activity");
    const thread = screen.getByRole("list", { name: "Thread" });
    const turns = within(thread)
      .getAllByRole("listitem")
      .filter((li) => li.parentElement === thread);
    expect(turns).toHaveLength(2);
    expect(turns[0]).toHaveTextContent("Compare three green electricity offers");
    expect(turns[0]).toHaveTextContent("The second offer is the cheapest");
    expect(within(turns[0] as HTMLElement).getByRole("link", { name: /bill-september\.pdf/ })).toHaveAttribute(
      "href",
      "/api/v1/tasks/t-3f2a1c/turns/u-3f2a-1/files/0",
    );
    expect(within(turns[0] as HTMLElement).getByRole("link", { name: /energy-offers\.pdf/ })).toHaveAttribute(
      "href",
      "/api/v1/tasks/t-3f2a1c/turns/u-3f2a-1/files/2",
    );
    expect(turns[1]).toHaveTextContent("And with off-peak hours?");
    expect(turns[1]).toHaveTextContent("Written on Telegram");
    expect(screen.getByRole("region", { name: "Notes" })).toHaveTextContent("Current contract: 9 kVA");
    expect(screen.getByRole("complementary", { name: "About this task" })).toHaveTextContent("Mathis");
  });

  it("answers the question a task waits on, which starts its next turn", async () => {
    const user = userEvent.setup();
    renderApp("/tasks/t-4410aa");
    expect(await screen.findByText(/I can't find the optician's invoice/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Answer…" }));
    const dialog = await screen.findByRole("dialog", { name: "Answer the task" });
    await user.type(within(dialog).getByRole("textbox"), "It is in the Gmail account, from Optique Lumière.{Enter}");
    await waitFor(() => expect(task("t-4410aa").state).toBe("working"));
    expect(task("t-4410aa").thread.at(-1)).toMatchObject({
      instruction: "It is in the Gmail account, from Optique Lumière.",
      by: { id: "mathis" },
    });
    expect(await screen.findByText("Sent: the task is back at work.")).toBeInTheDocument();
    expect(await screen.findByText("It is in the Gmail account, from Optique Lumière.")).toBeInTheDocument();
  });

  it("says why an instruction was refused, and keeps what was written", async () => {
    server.use(
      http.post("/api/v1/tasks/:id/instructions", () =>
        HttpResponse.json(
          {
            error: {
              code: "person_required",
              message_id: "error-person-required",
              args: {},
              message: "A member or guest account must be linked to a person of the household.",
            },
          } satisfies ErrorOut,
          { status: 403 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderApp("/tasks/t-3f2a1c");
    await user.click(await screen.findByRole("button", { name: "Continue…" }));
    const dialog = await screen.findByRole("dialog", { name: "Ask for more" });
    await user.type(within(dialog).getByRole("textbox"), "Add a fourth supplier.{Enter}");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("must be linked to a person");
    expect(within(dialog).getByRole("textbox")).toHaveValue("Add a fourth supplier.");
  });

  it("stops the work in progress once confirmed; the task stays, ready for more", async () => {
    const user = userEvent.setup();
    renderApp("/tasks/t-88b07e");
    await user.click(await screen.findByRole("button", { name: "Stop…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(task("t-88b07e").state).toBe("ready"));
    expect(task("t-88b07e").thread.at(-1)?.status).toBe("stopped");
    expect(await screen.findByRole("button", { name: "Continue…" })).toBeInTheDocument();
  });

  it("renames a task", async () => {
    const user = userEvent.setup();
    renderApp("/tasks/t-c1a9de");
    await user.click(await screen.findByRole("button", { name: "Rename…" }));
    const dialog = await screen.findByRole("dialog", { name: "Rename the task" });
    const title = within(dialog).getByRole("textbox", { name: "Title" });
    await user.clear(title);
    await user.type(title, "Dashboard upgrade{Enter}");
    expect(await screen.findByRole("heading", { name: "Dashboard upgrade", level: 1 })).toBeInTheDocument();
    expect(task("t-c1a9de").title).toBe("Dashboard upgrade");
  });
});

describe("tasks in Ongoing", () => {
  it("lists them by where they stand: the question first, the work under way, then the ready ones", async () => {
    renderApp("/activity");
    const waiting = await screen.findByRole("region", { name: /^Waiting for an answer/ });
    expect(await within(waiting).findByText(/I can't find the optician's invoice/)).toBeInTheDocument();
    const running = screen.getByRole("region", { name: /^Being done/ });
    expect(within(running).getByText("Reading the “Léa's recipes” MCP server.")).toBeInTheDocument();
    const ready = screen.getByRole("region", { name: /^Ready/ });
    expect(within(ready).getByText("Green electricity offers")).toBeInTheDocument();
    expect(within(ready).queryByText("Jules's homework")).not.toBeInTheDocument();
    const gym = within(ready).getByRole("button", { name: /Gym membership cancellation/ });
    expect(gym).toHaveTextContent("failed");
  });

  it("reorients a working task from its sheet, then archives a ready one and finds it among the archived", async () => {
    const user = userEvent.setup();
    renderApp("/activity");
    const running = await screen.findByRole("region", { name: /^Being done/ });
    await user.click(await within(running).findByRole("button", { name: /Week's shopping list/ }));
    const sheet = await screen.findByRole("dialog", { name: "Week's shopping list" });
    await user.type(
      await within(sheet).findByRole("textbox", { name: "Reorient the work in progress…" }),
      "No meat this week.{Enter}",
    );
    expect(await within(sheet).findByText("No meat this week.")).toBeInTheDocument();
    expect(task("t-88b07e").thread.at(-1)?.steered.at(-1)).toMatchObject({
      instruction: "No meat this week.",
      by: { id: "mathis" },
    });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    const ready = screen.getByRole("region", { name: /^Ready/ });
    await user.click(within(ready).getByRole("button", { name: /Dashboard dependencies/ }));
    const opened = await screen.findByRole("dialog", { name: "Dashboard dependencies" });
    await user.click(within(opened).getByRole("button", { name: "Archive…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Archive" }));
    await waitFor(() => expect(task("t-c1a9de").state).toBe("archived"));
    await waitFor(() => expect(within(ready).queryByText("Dashboard dependencies")).not.toBeInTheDocument());
    await user.click(within(ready).getByRole("button", { name: /Archived/ }));
    expect(await within(ready).findByText("Dashboard dependencies")).toBeInTheDocument();
    expect(within(ready).getByText("Jules's homework")).toBeInTheDocument();
  });
});
