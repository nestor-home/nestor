import { journalItem } from "./adapt";
import { url } from "./client";
import type { JournalItemDto } from "./dto";
import type { JournalItem } from "./types";

export type LiveStatus = "connecting" | "open" | "closed";

export interface JournalStream {
  /** Calls `onItem` for every new journal item until the returned function is called. */
  subscribe(onItem: (item: JournalItem) => void, onStatus: (status: LiveStatus) => void): () => void;
}

/**
 * `GET /journal/stream` as Server-Sent Events: one `item` event per journal item, shaped like the
 * paged list. The browser reconnects by itself; `closed` is reported while it is retrying.
 */
export const eventSourceStream: JournalStream = {
  subscribe(onItem, onStatus) {
    onStatus("connecting");
    const source = new EventSource(url("/journal/stream"), { withCredentials: true });
    source.onopen = () => onStatus("open");
    source.onerror = () => onStatus(source.readyState === EventSource.CLOSED ? "closed" : "connecting");
    source.addEventListener("item", (event) => {
      try {
        onItem(journalItem(JSON.parse((event as MessageEvent<string>).data) as JournalItemDto));
      } catch {
        // a malformed line is dropped: the paged list remains the reference
      }
    });
    return () => {
      source.close();
      onStatus("closed");
    };
  },
};
