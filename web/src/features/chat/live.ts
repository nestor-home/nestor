/**
 * The answers being written, one per chat, kept outside React: leaving a chat does not stop following its answer,
 * and coming back shows it where it is. Each is read from the API's stream (one `ChatStreamOut` per line) until
 * `done`; the chat then reads the messages from the journal and the answer is dropped.
 */
import { useSyncExternalStore } from "react";
import { type ChatMessageIn, type ChatStreamPart, type Id, messageOf } from "@/api";
import { ApiError, client, toError } from "@/api/client";
import { tr } from "@/i18n/runtime";

export interface LiveAnswer {
  /** what was sent, shown until the chat has it; none when following an answer started elsewhere */
  sent: ChatMessageIn | null;
  /** the journal position this turn's entries come after: the message sent (or followed), then its answer */
  after: number;
  /** its messages, the last one still being written while `writing` */
  messages: string[];
  writing: boolean;
  state: "waiting" | "writing" | "failed" | "done";
  error: string | null;
}

const answers = new Map<Id, LiveAnswer>();
const listeners = new Set<() => void>();

function set(chat: Id, change: (answer: LiveAnswer) => LiveAnswer): void {
  const answer = answers.get(chat);
  if (!answer) return;
  answers.set(chat, change(answer));
  notify();
}

function drop(chat: Id): void {
  if (answers.delete(chat)) notify();
}

let frame = 0;

/** Tell the pages, once per frame however many words came: a fast stream does not render each one. */
function notify(): void {
  if (frame) return;
  frame = requestAnimationFrame(() => {
    frame = 0;
    for (const listener of listeners) listener();
  });
}

export function useLiveAnswer(chat: Id | null): LiveAnswer | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => (chat ? (answers.get(chat) ?? null) : null),
  );
}

/**
 * Write in `chat` and follow the answer; resolves once the message is taken, throws the API's refusal (a chat still
 * answering). `settled` runs once the answer is over, before it is dropped: the chat then reads its messages.
 */
export async function send(chat: Id, body: ChatMessageIn, after: number, settled: () => Promise<void>): Promise<void> {
  const call = client.POST("/api/v1/chats/{chat}/messages", { params: { path: { chat } }, body, parseAs: "stream" });
  await follow(chat, { sent: body, after }, call, settled);
}

/** Follow the answer being written in `chat`, from its start, if there is one. */
export async function rejoin(chat: Id, after: number, settled: () => Promise<void>): Promise<void> {
  if (answers.has(chat)) return;
  const call = client.GET("/api/v1/chats/{chat}/answer", { params: { path: { chat } }, parseAs: "stream" });
  await follow(chat, { sent: null, after }, call, settled);
}

/** Starts following: resolves once the server took the message (or has no answer to follow), then reads on. */
async function follow(
  chat: Id,
  start: Pick<LiveAnswer, "sent" | "after">,
  call: Promise<{ response: Response }>,
  settled: () => Promise<void>,
): Promise<void> {
  answers.set(chat, { ...start, messages: [], writing: false, state: "waiting", error: null });
  notify();
  let response: Response;
  try {
    ({ response } = await call);
  } catch {
    drop(chat);
    throw new ApiError(0, "network", tr("error-network"), "error-network");
  }
  if (response.status === 204) return drop(chat);
  if (!response.ok || !response.body) {
    drop(chat);
    throw toError(response.status, await response.json().catch(() => undefined));
  }
  void read(chat, response.body, settled);
}

async function read(chat: Id, body: ReadableStream<Uint8Array>, settled: () => Promise<void>): Promise<void> {
  try {
    for await (const part of parts(body)) set(chat, (answer) => step(answer, part));
  } catch (error) {
    set(chat, (answer) => ({ ...answer, writing: false, state: "failed", error: messageOf(error) }));
  }
  await settled();
  if (answers.get(chat)?.state !== "failed") drop(chat);
}

/** Forget a failed answer once its chat has been read again. */
export function dismiss(chat: Id): void {
  drop(chat);
}

function step(answer: LiveAnswer, part: ChatStreamPart): LiveAnswer {
  switch (part.type) {
    case "text": {
      const messages = answer.writing ? answer.messages.slice(0, -1) : answer.messages;
      const current = answer.writing ? (answer.messages.at(-1) ?? "") : "";
      return { ...answer, messages: [...messages, current + (part.text ?? "")], writing: true, state: "writing" };
    }
    case "end":
      return { ...answer, writing: false };
    case "failed":
      return { ...answer, writing: false, state: "failed", error: tr("chat-failed") };
    case "done":
      return answer.state === "failed" ? answer : { ...answer, writing: false, state: "done" };
  }
}

async function* parts(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatStreamPart> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end = buffer.indexOf("\n");
    while (end >= 0) {
      const line = buffer.slice(0, end).trim();
      buffer = buffer.slice(end + 1);
      if (line) yield JSON.parse(line) as ChatStreamPart;
      end = buffer.indexOf("\n");
    }
  }
}
