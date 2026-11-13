import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { renderApp } from "@/test/render";

describe("the system page", () => {
  it("names the model that answers when another fails", async () => {
    const sonnet = db.system.components.find((c) => c.name === "sonnet");
    if (!sonnet) throw new Error("the sonnet model is in the mocks");
    sonnet.fallback = "haiku";
    renderApp("/system");
    expect(await screen.findByText("fallback: haiku")).toBeInTheDocument();
  });
});
