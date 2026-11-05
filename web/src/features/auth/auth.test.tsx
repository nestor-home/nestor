import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("signing in", () => {
  it("refuses a wrong password, then lands where the person was going", async () => {
    db.signedIn = null;
    const user = userEvent.setup();
    const { router } = renderApp("/login?next=%2Fwatches");
    await user.type(await screen.findByLabelText("Login"), "lea");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong address or password.");

    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Password"), "nestor");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/watches"));
  });

  it("never follows a `next` to another site", async () => {
    db.signedIn = null;
    const user = userEvent.setup();
    const { router } = renderApp("/login?next=%2F%2Fevil.example");
    await user.type(await screen.findByLabelText("Login"), "mathis");
    await user.type(screen.getByLabelText("Password"), "nestor");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/journal"));
  });
});

describe("accepting an invitation", () => {
  it("checks the password before creating the account", async () => {
    db.signedIn = null;
    const user = userEvent.setup();
    const { router } = renderApp("/invitation/inv-odile");
    expect(await screen.findByText(/ as /)).toHaveTextContent("member, for Odile");
    expect(screen.getByLabelText("Login")).toHaveValue("odile");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.type(screen.getByLabelText("Confirm the password"), "short");
    await user.click(screen.getByRole("button", { name: "Accept the invitation" }));
    expect(screen.getByRole("alert")).toHaveTextContent("At least 12 characters.");

    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Password"), "my grandmother's tea");
    await user.clear(screen.getByLabelText("Confirm the password"));
    await user.type(screen.getByLabelText("Confirm the password"), "my grandmother's tee");
    await user.click(screen.getByRole("button", { name: "Accept the invitation" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The passwords do not match.");

    await user.clear(screen.getByLabelText("Confirm the password"));
    await user.type(screen.getByLabelText("Confirm the password"), "my grandmother's tea");
    await user.click(screen.getByRole("button", { name: "Accept the invitation" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/journal"));
    expect(db.accounts.some((a) => a.login === "odile" && a.role === "member" && a.person === "odile")).toBe(true);
  });

  it("explains a used or unknown link", async () => {
    db.signedIn = null;
    renderApp("/invitation/inv-perime");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This invitation does not exist, has expired or was already used.",
    );
  });
});
