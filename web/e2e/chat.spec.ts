import { expect, test } from "./clock";

/** The chat in a real browser: writing with @ tags, the answer as it streams, and stopping it. */
test.describe("the chat", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/chat");
    await page.evaluate(() => sessionStorage.clear());
    await page.goto("/chat");
  });

  test("a message names with @ as tags, is sent with Enter, and opens its chat", async ({ page }) => {
    const editor = page.getByRole("textbox", { name: "Message Richie" });
    await editor.click();
    await page.keyboard.type("ask @cod");
    await expect(page.getByRole("button", { name: /codex/ })).toBeVisible();
    await page.keyboard.press("Enter");
    await page.keyboard.type("to update the SDK, then check @gma");
    await page.keyboard.press("Tab");
    await expect(editor.getByText("mathis@gmail.com")).toBeVisible();
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/chat\/[\w-]+$/);
    const sent = page.locator(".rounded-br-md").last();
    await expect(sent).toContainText("codex");
    await expect(sent).toContainText("mathis@gmail.com");
    await expect(page.getByText("It's in hand; I'll come back here when it's done.")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Chats" }).getByRole("link").first()).toContainText("ask @codex");
  });

  test("Stop ends the answer where it is, and the chat says so", async ({ page }) => {
    const editor = page.getByRole("textbox", { name: "Message Richie" });
    await editor.click();
    await page.keyboard.type("what can you do?");
    await page.keyboard.press("Enter");
    const stop = page.getByRole("button", { name: "Stop" });
    await expect(stop).toBeVisible();
    await expect(page.getByText("Here is what I can do")).toBeVisible();
    await stop.click();
    await expect(page.getByText("Stopped")).toBeVisible();
    await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
  });
});
