/** The home, reminders and messages: what the admin shows of them and what a person does there. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

describe("the home", () => {
  it("shows who is where, its rooms with their satellites, and which actions need a go-ahead", async () => {
    renderApp("/house");
    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeInTheDocument();
    expect(await screen.findByText(/who is in which room/)).toBeInTheDocument();
    const people = screen.getByRole("region", { name: /^Who is where/ });
    expect(within(people).getByText("not tied: presence unknown")).toBeInTheDocument();
    const rooms = screen.getByRole("region", { name: /^Rooms/ });
    expect(within(rooms).getByText("Living room Reachy")).toBeInTheDocument();
    expect(within(rooms).getByText("Mathis, Jules")).toBeInTheDocument();
    const actions = screen.getByRole("region", { name: /^Actions/ });
    expect(within(actions).getAllByText("confirmed depending on its target")).toHaveLength(3);
    expect(screen.getByText("binary_sensor.garage_motion")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Configure" })).toHaveAttribute("href", "/config/home");
  });

  it("says when no home system is plugged in, and where to plug one", async () => {
    db.home = null;
    renderApp("/house");
    expect(await screen.findByText("No home system plugged in.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Configure" })).toHaveAttribute("href", "/config/home");
  });
});

describe("reminders", () => {
  it("lists the one-offs and the recurring ones, and cancels one once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/schedules");
    const recurring = await screen.findByRole("region", { name: /^Recurring/ });
    expect(within(recurring).getByText("Saturday, Sunday · 09:00")).toBeInTheDocument();
    expect(within(recurring).getByText("every day · 10:00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel “Remind Mathis to buy bread.”" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancel the reminder" }),
    );
    await waitFor(() => expect(db.schedules.map((s) => s.id)).not.toContain("sc-bread"));
    expect(await screen.findByText("Cancelled: it will not run again.")).toBeInTheDocument();
  });
});

describe("messages", () => {
  it("lets the person approve a sensitive action asked aloud, and shows what waits elsewhere", async () => {
    const user = userEvent.setup();
    renderApp("/messages");
    const waiting = await screen.findByRole("region", { name: /^To confirm/ });
    expect(await within(waiting).findByText(/Front door/)).toBeInTheDocument();
    expect(screen.getByText("“Do you need the car tomorrow?”")).toBeInTheDocument();
    expect(screen.getByText("from Léa to Odile")).toBeInTheDocument();
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
    renderApp("/messages");
    await user.click(await screen.findByRole("button", { name: "Refuse" }));
    expect(await screen.findByText(/it was answered, or it expired/)).toBeInTheDocument();
  });
});
