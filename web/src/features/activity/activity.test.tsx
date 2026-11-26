/** Ongoing: what waits for an answer, what runs, what is planned and what is watched, and acting on each. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

const part = (name: RegExp) => screen.findByRole("region", { name });

describe("ongoing", () => {
  it("lets the person approve a sensitive action asked aloud, and shows what waits elsewhere", async () => {
    const user = userEvent.setup();
    renderApp("/activity");
    const waiting = await part(/^Waiting for an answer/);
    expect(await within(waiting).findByText(/Front door/)).toBeInTheDocument();
    expect(within(waiting).getByText("“Do you need the car tomorrow?”")).toBeInTheDocument();
    expect(within(waiting).getByText("from Léa to Odile")).toBeInTheDocument();
    await user.click(within(waiting).getByRole("button", { name: "Approve" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(db.confirmations).toEqual([]));
    expect(await screen.findByText("Approved: it is done.")).toBeInTheDocument();
  });

  it("says why an answer did not go through", async () => {
    server.use(
      http.post("/api/v1/confirmations/:id/answer", () =>
        HttpResponse.json(
          {
            error: {
              code: "confirmation_unknown",
              message_id: "error-confirmation-unknown",
              message: "This request no longer waits for your go-ahead: it was answered, or it expired.",
              args: {},
            },
          },
          { status: 404 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderApp("/activity");
    await user.click(await screen.findByRole("button", { name: "Refuse" }));
    expect(await screen.findByText(/no longer waits for your go-ahead/)).toBeInTheDocument();
  });

  it("opens a reminder in place with when it runs, and cancels it once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/activity");
    const planned = await part(/^Planned/);
    expect(await within(planned).findByText("Saturday, Sunday · 09:00")).toBeInTheDocument();
    expect(within(planned).getByText("every day · 10:00")).toBeInTheDocument();
    await user.click(within(planned).getByRole("button", { name: /Buy bread/ }));
    const sheet = await screen.findByRole("dialog", { name: "Buy bread" });
    await user.click(within(sheet).getByRole("button", { name: "Cancel the reminder" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancel the reminder" }),
    );
    await waitFor(() => expect(db.schedules.map((s) => s.id)).not.toContain("sc-bread"));
    expect(await screen.findByText("Cancelled: it will not run again.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("keeps one lane when asked: only what is watched, with how often each fired", async () => {
    const user = userEvent.setup();
    renderApp("/activity");
    await part(/^Being watched/);
    await user.click(screen.getByRole("button", { name: /^Watches/ }));
    expect(screen.queryByRole("region", { name: /^Planned/ })).not.toBeInTheDocument();
    const watched = await part(/^Being watched/);
    expect(within(watched).getAllByRole("button").length).toBe(db.watches.length);
  });
});
