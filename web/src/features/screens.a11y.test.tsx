/** Every screen, and its main overlays open, passes axe: names, roles, labels, no nested controls. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, vi } from "vitest";
import { expectAccessible } from "@/test/axe";
import { microphone, speak } from "@/test/microphone";
import { renderApp, settle } from "@/test/render";

vi.mock("@/lib/audio/microphone", () => import("@/test/microphone").then((m) => m.module()));
beforeEach(() => microphone.reset());

const SCREENS: [string, string | RegExp][] = [
  ["/", /Hello|Good evening|Good night|Good morning/],
  ["/journal", "Journal"],
  ["/chat", "New chat"],
  ["/chat/c-dinner", /Turn on the kitchen lights/],
  ["/journal?conversation=conv-s-elec", "Journal"],
  ["/people", "People"],
  ["/people/lea", "Léa"],
  ["/people/mathis", "Mathis"],
  ["/people/jules", "Jules"],
  ["/house", "Home"],
  ["/schedules", "Reminders"],
  ["/messages", "Messages"],
  ["/memories", "Memories"],
  ["/watches", "Watches"],
  ["/watches/w-9d41", /News from the school/],
  ["/tasks", "Tasks"],
  ["/tasks/t-3f2a1c", /green electricity/],
  ["/connections", "Connections"],
  ["/connections/catalogue", "Connections"],
  ["/connections/c-gmail-mathis", /mathis\.lambert27@gmail\.com/],
  ["/connections/c-gmail-mathis/tools", /mathis\.lambert27@gmail\.com/],
  ["/satellites", "Satellites"],
  ["/satellites/reachy-living-room", /Living room Reachy/],
  ["/system", "System"],
  ["/accounts", "Accounts"],
  ["/config/persona", "Configuration"],
  ["/config/household", "Configuration"],
  ["/config/conversation", "Configuration"],
  ["/config/models", "Configuration"],
  ["/config/channels", "Configuration"],
  ["/config/tools", "Configuration"],
  ["/config/inbound", "Configuration"],
  ["/config/home", "Configuration"],
  ["/config/admin", "Configuration"],
  ["/config/secrets", "Configuration"],
  ["/config/history", "Configuration"],
];

describe("accessibility of every screen", () => {
  it.each(SCREENS)("%s", async (path, heading) => {
    const { queryClient } = renderApp(path);
    await screen.findByRole("heading", { level: 1, name: heading });
    await screen.findByRole("navigation", { name: "Sections" });
    await settle(queryClient);
    await expectAccessible();
  });

  it("the journal with a facet popover and the event drawer open", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderApp("/journal");
    await user.click(await screen.findByRole("button", { name: /^Person/ }));
    await screen.findByRole("option", { name: /Léa/ });
    await settle(queryClient);
    await expectAccessible();
    await user.keyboard("{Escape}");
    await settle(queryClient);
    const [entry] = await screen.findAllByRole("button", { name: / said/ });
    if (entry) await user.click(entry);
    await screen.findByRole("heading", { name: "JSON" });
    await settle(queryClient);
    await expectAccessible();
  });

  it("a component's sheet, with a problem shown at its field", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderApp("/config/channels");
    await user.click(await screen.findByRole("button", { name: "Edit Satellites" }));
    const sheet = await screen.findByRole("dialog", { name: "Satellites" });
    await user.clear(within(sheet).getByRole("spinbutton", { name: "Port" }));
    await user.type(within(sheet).getByRole("spinbutton", { name: "Port" }), "70000");
    await within(sheet).findByText("Port: ≤ 65535");
    await settle(queryClient);
    await expectAccessible();
  });

  it("the add-a-satellite sheet, choosing then following an enrollment code", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderApp("/satellites");
    await user.click(await screen.findByRole("button", { name: "Add a satellite" }));
    const sheet = await screen.findByRole("dialog", { name: "Add a satellite" });
    await within(sheet).findByRole("button", { name: /^QR code/ });
    await settle(queryClient);
    await expectAccessible();
    await user.click(within(sheet).getByRole("button", { name: /^QR code/ }));
    await user.click(within(sheet).getByRole("button", { name: "Start" }));
    await within(sheet).findByRole("img", { name: /QR code of the pairing URI/ });
    await settle(queryClient);
    await expectAccessible();
  });

  it("the connect sheet", async () => {
    const { queryClient } = renderApp("/connections/catalogue?connect=imap");
    await screen.findByRole("dialog", { name: /Mailbox/ });
    await settle(queryClient);
    await expectAccessible();
  });

  it("the approve-a-satellite dialog", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderApp("/satellites");
    const [approve] = await screen.findAllByRole("button", { name: /Approve/ });
    if (approve) await user.click(approve);
    await screen.findByRole("dialog");
    await settle(queryClient);
    await expectAccessible();
  });

  it("the voice recording, at each of its steps", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderApp("/people/jules");
    await user.click(await screen.findByRole("button", { name: "Record their voice" }));
    const dialog = await screen.findByRole("dialog", { name: "Record Jules's voice" });
    await settle(queryClient);
    await expectAccessible();
    await user.click(within(dialog).getByRole("button", { name: "Start" }));
    await within(dialog).findByRole("combobox", { name: "Microphone" });
    await speak();
    await within(dialog).findByText("I can hear you well.");
    await expectAccessible();
    await user.click(within(dialog).getByRole("button", { name: "Continue" }));
    await within(dialog).findByRole("progressbar", { name: "Phrases kept" });
    await speak();
    await within(dialog).findByText("Phrase 2 of 5");
    await expectAccessible();
    await speak(); // refused once by the mock
    await within(dialog).findByText("That was a bit short. Once more?");
    for (const n of [3, 4, 5]) {
      await speak();
      await within(dialog).findByText(`Phrase ${n} of 5`);
    }
    await speak();
    await within(dialog).findByRole("button", { name: "Try it" });
    await expectAccessible();
  });
});
