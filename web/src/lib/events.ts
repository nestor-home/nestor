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
  taskStarted: ["journal-task-created"],
  taskInstructed: ["journal-task-turn-started"],
  taskSteered: ["journal-task-steered"],
  taskProgressed: [
    "journal-task-turn-attached",
    "journal-task-turn-step",
    "journal-task-turn-file-added",
    "journal-task-noted",
  ],
  taskEnded: ["journal-task-turn-ended"],
  taskDelivered: ["journal-task-turn-delivered"],
  taskReminded: ["journal-task-reminded"],
  watchCreated: ["journal-watch-created"],
  watchSorted: ["journal-watch-sorted"],
  watchTriggered: ["journal-watch-triggered"],
  considered: ["journal-delivery-considered"],
  delivered: ["journal-delivered"],
  withheld: ["journal-delivery-withheld"],
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
