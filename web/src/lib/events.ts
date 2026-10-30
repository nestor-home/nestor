/**
 * What a journal event is, read from its message id (the server's `journal.ftl`, its
 * catalogue): one name per kind of line, the one every screen asks about.
 */
import type { JournalItem } from "@/api";

const IDS = {
  userTurn: ["journal-user-said"],
  answer: ["journal-assistant-answered", "journal-assistant-interrupted"],
  interrupted: ["journal-assistant-interrupted"],
  cut: ["journal-answer-cut"],
  fallback: ["journal-fallback"],
  toolCalled: ["journal-tool-called"],
  toolDone: ["journal-tool-completed", "journal-tool-failed"],
  taskStarted: ["journal-task-started"],
  taskProgressed: ["journal-task-progressed", "journal-task-attached"],
  taskEnded: ["journal-task-ended"],
  taskDelivered: ["journal-task-delivered"],
  watchCreated: ["journal-watch-created"],
  watchTriggered: ["journal-watch-triggered"],
  considered: ["journal-delivery-considered"],
  delivered: ["journal-delivered"],
  deliveryFailed: ["journal-delivery-failed"],
  memory: ["journal-memory-recorded"],
  presence: ["journal-presence-changed"],
  speech: ["journal-speech-activity"],
} as const;

export type EventSort = keyof typeof IDS;

export function is(item: Pick<JournalItem, "message">, sort: EventSort): boolean {
  return (IDS[sort] as readonly string[]).includes(item.message.id);
}

/** Started a story of its own (a task, a watch) from inside a conversation. */
export const starts = (item: Pick<JournalItem, "message">) => is(item, "taskStarted") || is(item, "watchCreated");
