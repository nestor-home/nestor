/** The chat: its list, a chat read from the journal (words, tags, tools, files, Markdown), and when it is off. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/mocks/server";
import { renderApp } from "@/test/render";

describe("the chat", () => {
  it("lists the chats by day and finds one by its words", async () => {
    const user = userEvent.setup();
    renderApp("/chat");
    const list = await screen.findByRole("navigation", { name: "Chats" });
    await screen.findByRole("textbox", { name: "Message Richie" }); // the composer takes the focus once, first
    expect(await within(list).findByText("Today")).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: /Why are its leaves turning yellow/ })).toBeInTheDocument();
    await user.type(within(screen.getByRole("complementary", { name: "Chats" })).getByRole("searchbox"), "contract");
    expect(within(list).getAllByRole("link")).toHaveLength(1);
    expect(within(list).getByRole("link", { name: /water damage/ })).toBeInTheDocument();
  });

  it("reads a chat: the answer in Markdown, the tools called on the way, opened on what they got", async () => {
    const user = userEvent.setup();
    renderApp("/chat/c-dinner");
    expect(await screen.findByRole("table")).toHaveTextContent("Omelette");
    expect(screen.getByText("Leek and comté quiche", { exact: false })).toBeInTheDocument();
    const call = screen.getByRole("button", { name: /homeassistant__HassTurnOn/ });
    expect(call).toHaveTextContent("Done in");
    await user.click(call);
    expect(await screen.findByText(/"area": "kitchen"/)).toBeVisible();
    expect(screen.getByRole("button", { name: "copy" })).toBeInTheDocument();
  });

  it("shows a photo, plays a voice message with what it said, and offers a file to download", async () => {
    renderApp("/chat/c-plant");
    expect(await screen.findByRole("img", { name: "plant.png" })).toBeInTheDocument();
    renderApp("/chat/c-voice");
    expect(await screen.findByText("Remind me to call grandma on Sunday at ten.")).toBeInTheDocument();
    renderApp("/chat/c-insurance");
    expect(await screen.findByRole("link", { name: /home-insurance-2026\.pdf/ })).toHaveAttribute("download");
    expect(screen.getByRole("note")).toHaveTextContent("Richie comes back: task 3f2a completed");
  });

  it("says how to turn the chat on when the instance has none", async () => {
    server.use(
      http.get("/api/v1/chats", () =>
        HttpResponse.json(
          {
            error: {
              code: "chat_off",
              message_id: "error-chat-off",
              message: "The chat is off: add a channel of kind web under channels in the configuration.",
              args: {},
            },
          },
          { status: 404 },
        ),
      ),
    );
    renderApp("/chat");
    expect(await screen.findByRole("alert")).toHaveTextContent("kind: web");
  });
});
