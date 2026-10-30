import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { db } from "@/mocks/db";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

describe("tasks and watches", () => {
  it("tells a task from its request to its delivery", async () => {
    renderApp("/tasks/t-3f2a1c");
    expect(await screen.findByRole("heading", { name: /Comparer trois offres/, level: 1 })).toBeInTheDocument();
    const chain = await screen.findByRole("article");
    for (const step of ["confiée", "terminée", "décision", "dit à voix haute"])
      expect(within(chain).getByText(step)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /une conversation/ })).toHaveAttribute("href", "/journal?session=s-elec");
  });

  it("stops a running task once confirmed", async () => {
    const user = userEvent.setup();
    renderApp("/tasks/t-4410aa");
    await user.click(await screen.findByRole("button", { name: "Arrêter…" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Arrêter" }));
    await waitFor(() => expect(db.tasks.find((t) => t.id === "t-4410aa")?.status).toBe("cancelled"));
  });

  it("keeps the dialog open with the reason when stopping fails", async () => {
    server.use(
      http.post("/api/v1/tasks/:id/cancel", () =>
        HttpResponse.json(
          { error: { code: "executor_unreachable", message: "L'exécutant ne répond pas." } },
          { status: 502 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderApp("/tasks/t-4410aa");
    await user.click(await screen.findByRole("button", { name: "Arrêter…" }));
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Arrêter" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("L'exécutant ne répond pas.");
  });

  it("offers to retry when Nestor is unreachable", async () => {
    server.use(http.get("/api/v1/tasks", () => HttpResponse.error()));
    const user = userEvent.setup();
    renderApp("/tasks");
    expect(await screen.findByRole("alert")).toHaveTextContent("Nestor ne répond pas");
    server.resetHandlers();
    await user.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByText(/Préparer la liste de courses/)).toBeInTheDocument();
  });

  it("tells what a watch found and how it was announced", async () => {
    renderApp("/watches/w-9d41");
    const articles = await screen.findAllByRole("article");
    const chain = articles.find((a) => a.textContent?.includes("déclenchée")) as HTMLElement;
    // the conversation where Léa answered is linked to the watch too, as its own thread
    expect(articles.some((a) => a.textContent?.includes("J'irai le chercher en rentrant"))).toBe(true);
    expect(chain).toHaveTextContent("pourquoi : Léa est dans la pièce « salon »");
    expect(chain).toHaveTextContent("relance");
    expect(chain).toHaveTextContent("pourquoi : Léa n'est pas à la maison");
  });

  it("points to the catalogue when no source can feed a watch", async () => {
    db.watches = [];
    db.connectors = db.connectors.map((c) => ({ ...c, inbound: [] }));
    renderApp("/watches");
    expect(await screen.findByText("Aucune veille active.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "connectez une boîte mail" })).toHaveAttribute(
      "href",
      "/connections/catalogue",
    );
  });
});
