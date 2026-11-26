/** Ongoing: what waits for an answer, what runs, the alerts kept and why each rang, and acting on each. */
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

  it("lists every alert in one place with what rings it and why it last rang", async () => {
    renderApp("/activity");
    const alerts = await part(/^Alerts/);
    expect(await within(alerts).findByText("Saturday, Sunday · 09:00")).toBeInTheDocument();
    expect(within(alerts).getByText("every day · 10:00")).toBeInTheDocument();
    expect(within(alerts).getByText("Until it has told something")).toBeInTheDocument();
    const machine = within(alerts).getByRole("button", { name: /Washing machine done/ });
    expect(machine).toHaveTextContent("The event washing-machine arrived: cycle · done");
    const school = within(alerts).getByRole("button", { name: /Jules's school/ });
    expect(school).toHaveTextContent("“Canteen menu for next week” matched");
  });

  it("opens an alert in place and cancels it once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/activity");
    const alerts = await part(/^Alerts/);
    await user.click(await within(alerts).findByRole("button", { name: /Samsung TV price/ }));
    const sheet = await screen.findByRole("dialog", { name: "Samsung TV price" });
    expect(within(sheet).getByText("Below €1,600")).toBeInTheDocument();
    expect(within(sheet).getByText("Rang 8 times")).toBeInTheDocument();
    await user.click(within(sheet).getByRole("button", { name: "Cancel the alert…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancel the alert" }));
    await waitFor(() => expect(db.alerts.map((a) => a.id)).not.toContain("a-tv"));
    expect(await screen.findByText("Cancelled: it will not ring again.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("keeps one lane when asked: only the alerts", async () => {
    const user = userEvent.setup();
    renderApp("/activity");
    await part(/^Alerts/);
    await user.click(screen.getByRole("button", { name: /^Alerts/ }));
    expect(screen.queryByRole("region", { name: /^Being done/ })).not.toBeInTheDocument();
    const alerts = await part(/^Alerts/);
    expect(within(alerts).getAllByRole("button").length).toBe(db.alerts.length);
  });
});
