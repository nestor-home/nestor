import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("memories", () => {
  it("files what the agent knows by place: the people, the house, the household, then projects and topics", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/memories");
    const jules = await screen.findByRole("region", { name: /^Jules/ });
    expect(within(jules).getByRole("button", { name: /Jules is allergic to peanuts\./ })).toBeInTheDocument();
    expect(within(jules).queryByText(/Odile comes for lunch/)).not.toBeInTheDocument();
    expect(within(jules).getByRole("link", { name: "Open Jules's page" })).toHaveAttribute("href", "/people/jules");
    const home = screen.getByRole("region", { name: /^Home/ });
    expect(within(home).getByText(/The gate code is only ever given out loud/)).toBeInTheDocument();
    const roof = screen.getByRole("region", { name: /^Roof works/ });
    expect(within(roof).getByText("project")).toBeInTheDocument();
    expect(within(roof).getByText(/The roofer comes back on Thursday/)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: /^Garden/ })).getByText("topic")).toBeInTheDocument();
    const order = screen
      .getAllByRole("region")
      .map((r) => r.getAttribute("aria-labelledby") ?? "")
      .map((id) => document.getElementById(id)?.textContent?.replace(/\d+$/, ""));
    expect(order.indexOf("Jules")).toBeLessThan(order.indexOf("Home"));
    expect(order.indexOf("Home")).toBeLessThan(order.indexOf("Household"));
    expect(order.indexOf("Household")).toBeLessThan(order.indexOf("Roof works"));
    expect(order.indexOf("Roof works")).toBeLessThan(order.indexOf("Garden"));
    await user.click(screen.getByRole("button", { name: "Odile" }));
    await waitFor(() => expect(router.state.location.search).toEqual({ about: "odile" }));
    expect(await screen.findByText(/Odile comes for lunch/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Jules is allergic to peanuts.")).not.toBeInTheDocument());
  });

  it("says until what a memory holds, and moves it to a new topic in a dialog", async () => {
    const user = userEvent.setup();
    renderApp("/memories");
    await user.click(await screen.findByRole("button", { name: /Léa wants oat milk/ }));
    const milk = await screen.findByRole("dialog", { name: /Léa wants oat milk/ });
    expect(within(milk).getByRole("link", { name: /its task ends/ })).toHaveAttribute("href", "/tasks/t-88b07e");
    await user.keyboard("{Escape}");

    await user.click(await screen.findByRole("button", { name: /Odile comes for lunch/ }));
    const sheet = await screen.findByRole("dialog", { name: /Odile comes for lunch/ });
    await user.click(within(sheet).getByRole("button", { name: "Move…" }));
    const dialog = await screen.findByRole("dialog", { name: "Move the memory" });
    await user.click(within(dialog).getByRole("combobox", { name: "Where it belongs" }));
    const options = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(options).toEqual(expect.arrayContaining(["Mathis", "Home", "Household", "Roof works (project)"]));
    await user.click(screen.getByRole("option", { name: "New topic…" }));
    const name = within(dialog).getByLabelText("Name");
    await user.type(name, "???");
    await user.click(within(dialog).getByRole("button", { name: "Move" }));
    expect(await within(dialog).findByText(/No such place/)).toBeInTheDocument();
    await user.clear(name);
    await user.type(name, "Family visits");
    await user.click(within(dialog).getByRole("button", { name: "Move" }));
    expect(await screen.findByText("Memory moved.")).toBeInTheDocument();
    expect(db.memories.find((m) => m.id === "m-04")?.place.path).toBe("topics/family-visits");
    await user.keyboard("{Escape}");
    const visits = await screen.findByRole("region", { name: /^Family visits/ });
    expect(within(visits).getByText(/Odile comes for lunch/)).toBeInTheDocument();
  });

  it("lists what was tidied lately, each opening its journal entry, and says when nothing was", async () => {
    renderApp("/memories");
    const tidied = await screen.findByRole("region", { name: /^Tidied lately/ });
    const merged = await within(tidied).findByRole("link", {
      name: /Merged into “Jules has handball practice on Wednesdays at 3 pm\.”/,
    });
    expect(merged).toHaveTextContent("Jules has handball on Wednesday afternoons.");
    const event = db.retired.find((r) => r.memory_id === "m-r1")?.event;
    expect(merged).toHaveAttribute("href", `/journal?event=${event}`);
    const stale = within(tidied).getByRole("link", { name: /Set aside as outdated/ });
    expect(stale).toHaveTextContent(/That service is past/);
    expect(within(tidied).getByRole("link", { name: /Set aside: its task ended/ })).toHaveTextContent(/Node 22/);
  });

  it("says nothing was tidied when nothing was", async () => {
    db.retired = [];
    renderApp("/memories");
    const tidied = await screen.findByRole("region", { name: /^Tidied lately/ });
    expect(await within(tidied).findByText("Nothing tidied lately.")).toBeInTheDocument();
  });

  it("opens a memory to say where it was learnt, and corrects it in a dialog", async () => {
    const user = userEvent.setup();
    renderApp("/memories?about=jules");
    await user.click(await screen.findByRole("button", { name: /Jules has handball practice on Wednesdays/ }));
    const practice = await screen.findByRole("dialog", { name: /Jules has handball practice/ });
    expect(within(practice).getByRole("link", { name: /Where it was learnt/ })).toHaveAttribute(
      "href",
      expect.stringContaining("session=s-jules"),
    );
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: /Jules is allergic to peanuts\./ }));
    const allergy = await screen.findByRole("dialog", { name: "Jules is allergic to peanuts." });
    await user.click(within(allergy).getByRole("button", { name: "Correct…" }));
    const dialog = await screen.findByRole("dialog", { name: "Correct the memory" });
    const text = within(dialog).getByLabelText("Memory text");
    await user.clear(text);
    await user.type(text, "Jules is allergic to peanuts and cashews.");
    await user.keyboard("{Meta>}{Enter}{/Meta}");
    expect(await screen.findByText("Memory corrected.")).toBeInTheDocument();
    expect(db.memories.find((m) => m.id === "m-01")?.text).toContain("cashews");
    expect(
      await screen.findByRole("dialog", { name: "Jules is allergic to peanuts and cashews." }),
    ).toBeInTheDocument();
  });

  it("forgets a memory only once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/memories");
    await user.click(await screen.findByRole("button", { name: /Odile comes for lunch/ }));
    const sheet = await screen.findByRole("dialog", { name: /Odile comes for lunch/ });
    await user.click(within(sheet).getByRole("button", { name: "Forget…" }));
    expect(db.memories.some((m) => m.id === "m-04")).toBe(true);
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Forget" }));
    await waitFor(() => expect(screen.queryByText(/Odile comes for lunch/)).not.toBeInTheDocument());
    expect(db.memories.some((m) => m.id === "m-04")).toBe(false);
  });

  it("searches in a dialog, says when nothing matches, and clears the search", async () => {
    const user = userEvent.setup();
    const { router } = renderApp("/memories");
    await user.click(await screen.findByRole("button", { name: "Search…" }));
    const dialog = await screen.findByRole("dialog", { name: "Search the memories" });
    await user.type(within(dialog).getByLabelText("Search"), "piscine");
    await user.click(within(dialog).getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No memory matches.")).toBeInTheDocument();
    expect(router.state.location.search).toEqual({ q: "piscine" });
    await user.click(screen.getByRole("button", { name: "Clear the search" }));
    expect(await screen.findByRole("region", { name: /^Jules/ })).toBeInTheDocument();
    expect(router.state.location.search).toEqual({});
  });
});
