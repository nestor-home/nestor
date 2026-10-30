import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { SIDEBAR_STORAGE_KEY } from "@/components/ui/sidebar";
import { renderApp } from "@/test/render";

function resize(width: number) {
  act(() => {
    Object.defineProperty(window, "innerWidth", { value: width, configurable: true });
    window.dispatchEvent(new Event("resize"));
  });
}

const sidebarState = () => document.querySelector("[data-slot=sidebar]")?.getAttribute("data-state");

describe("the sidebar", () => {
  afterEach(() => {
    localStorage.clear();
    resize(1024);
  });

  it("collapses to an icon rail from its button or with [, and remembers it", async () => {
    const user = userEvent.setup();
    const first = renderApp("/journal");
    await screen.findByRole("navigation", { name: "Sections" });
    expect(sidebarState()).toBe("expanded");
    await user.click(screen.getByRole("button", { name: "Réduire" }));
    expect(sidebarState()).toBe("collapsed");
    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe("collapsed");
    // the section names stay for assistive technologies, the agent shows its initial
    expect(screen.getByRole("link", { name: "Journal" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Richie, en ligne" })).toHaveTextContent("R");
    first.unmount();

    renderApp("/journal");
    await screen.findByRole("navigation", { name: "Sections" });
    expect(sidebarState()).toBe("collapsed");
    await user.keyboard("[[");
    expect(sidebarState()).toBe("expanded");
    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe("expanded");
  });

  it("does not collapse when [ is typed in a field", async () => {
    const user = userEvent.setup();
    renderApp("/journal");
    await user.type(await screen.findByLabelText("Chercher dans le journal"), "[[");
    expect(sidebarState()).toBe("expanded");
  });

  it("becomes a sheet opened from the top bar on a phone", async () => {
    resize(390);
    const user = userEvent.setup();
    const { router } = renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Ouvrir le menu" }));
    const sheet = await screen.findByRole("dialog");
    await user.click(within(sheet).getByRole("link", { name: "Souvenirs" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/memories"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
