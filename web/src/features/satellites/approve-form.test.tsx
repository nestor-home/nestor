import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { Approval } from "@/api";
import { I18nProvider } from "@/i18n";
import { pairing } from "@/mocks/fixtures";
import { server } from "@/mocks/server";
import { renderWithProviders } from "@/test/render";
import { ApproveForm, normaliseCode } from "./approve-form";

const [reachy] = pairing();
if (!reachy) throw new Error("fixture changed");

function captureApprovals() {
  const sent: Approval[] = [];
  server.events.on("request:start", async ({ request }) => {
    if (request.url.endsWith("/satellites/approvals")) sent.push((await request.clone().json()) as Approval);
  });
  return sent;
}

describe("approving a satellite", () => {
  it("accepts the code as people read it", () => {
    expect(normaliseCode("424 242")).toBe("424242");
    expect(normaliseCode("424-242")).toBe("424242");
  });

  it("refuses a code that is not six digits, without asking the server", async () => {
    const user = userEvent.setup();
    const sent = captureApprovals();
    renderWithProviders(
      <I18nProvider>
        <ApproveForm request={reachy} />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText("Code shown by the device"), "12a45");
    await user.click(screen.getByRole("button", { name: "Pair" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The code has 6 digits.");
    expect(screen.getByLabelText("Code shown by the device")).toHaveAttribute("aria-invalid", "true");
    expect(sent).toHaveLength(0);
  });

  it("sends the code and the narrowed capabilities for this pairing", async () => {
    const user = userEvent.setup();
    const sent = captureApprovals();
    renderWithProviders(
      <I18nProvider>
        <ApproveForm request={reachy} />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText("Code shown by the device"), "424 242");
    await user.click(screen.getByRole("checkbox", { name: /head movements/ }));
    await user.click(screen.getByRole("button", { name: "Pair" }));
    expect(await screen.findByText("Satellite reachy-mini-hallway paired in the hallway.")).toBeInTheDocument();
    expect(sent).toEqual([
      {
        code: "424242",
        capabilities: [
          "audio.capture",
          "audio.playback",
          "audio.speech_activity",
          "device.identify",
          "expression.emotion",
          "vision.person_detection",
        ],
        pairing_id: reachy.id,
      },
    ]);
  });

  it("says when no device waits for that code", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <I18nProvider>
        <ApproveForm request={reachy} />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText("Code shown by the device"), "000000");
    await user.click(screen.getByRole("button", { name: "Pair" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No device is waiting with this code");
  });

  it("explains an unreachable Nestor", async () => {
    server.use(http.post("/api/v1/satellites/approvals", () => HttpResponse.error()));
    const user = userEvent.setup();
    renderWithProviders(
      <I18nProvider>
        <ApproveForm request={reachy} />
      </I18nProvider>,
    );
    await user.type(screen.getByLabelText("Code shown by the device"), "424242");
    await user.click(screen.getByRole("button", { name: "Pair" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Nestor does not answer"));
  });
});
