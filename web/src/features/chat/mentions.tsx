/**
 * `@name` in a message: an executor to hand part of the work to ("ask @hermes where my project stands"). Typing `@`
 * offers the executors plugged in, filtered as the name is typed; the arrows choose, Enter or Tab writes it, Escape
 * closes. Sent, the names stand out in the message.
 */
import { useQuery } from "@tanstack/react-query";
import { type KeyboardEvent, type ReactNode, useMemo, useState } from "react";
import { type Mention, mentionsQuery } from "@/api";
import { useT } from "@/i18n";
import { BrandMark, brandColour, brandOf } from "@/lib/brands";
import { cn } from "@/lib/utils";

const TYPED = /(^|\s)@([\w-]*)$/;
const NAMED = /(@[\w-]+)/g;

interface Typing {
  start: number; // where its `@` is
  query: string;
}

/** The mention being typed just before the caret, if any. */
function typingAt(text: string, caret: number): Typing | null {
  const found = TYPED.exec(text.slice(0, caret));
  return found ? { start: caret - (found[2] ?? "").length - 1, query: found[2] ?? "" } : null;
}

export function useMentionPicker(text: string, caret: number, write: (text: string, caret: number) => void) {
  const { data: mentions = [] } = useQuery(mentionsQuery);
  const typing = typingAt(text, caret);
  const [active, setActive] = useState(0);
  const [closedAt, setClosedAt] = useState<number | null>(null);
  const query = typing?.query.toLocaleLowerCase();
  const options = useMemo(
    () => (query === undefined ? [] : mentions.filter((m) => m.name.toLocaleLowerCase().startsWith(query))),
    [mentions, query],
  );
  const open = typing !== null && options.length > 0 && closedAt !== typing.start;
  const current = Math.min(active, Math.max(0, options.length - 1));

  const choose = (mention: Mention) => {
    if (!typing) return;
    const inserted = `@${mention.name} `;
    write(text.slice(0, typing.start) + inserted + text.slice(caret), typing.start + inserted.length);
    setActive(0);
  };

  /** Handles the keys the list owns while it is open; true when the key was its. */
  const onKeyDown = (event: KeyboardEvent): boolean => {
    if (!open) return false;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current + step + options.length) % options.length);
    } else if ((event.key === "Enter" || event.key === "Tab") && !event.shiftKey) {
      const chosen = options[current];
      if (chosen) choose(chosen);
    } else if (event.key === "Escape") {
      setClosedAt(typing.start);
    } else return false;
    event.preventDefault();
    return true;
  };

  return { open, options, active: current, choose, onKeyDown, offered: mentions.length > 0 };
}

/**
 * The executors that match, above the composer. The textarea keeps the focus and its arrows move the choice; the
 * choice is said aloud as it moves.
 */
export function MentionList({
  options,
  active,
  onChoose,
}: {
  options: Mention[];
  active: number;
  onChoose: (mention: Mention) => void;
}) {
  const t = useT();
  const current = options[active];
  return (
    <div className="absolute right-0 bottom-full left-0 z-30 mb-2 animate-in overflow-hidden rounded-xl border border-rule-strong bg-paper-raised shadow-lg duration-150 fade-in-0 slide-in-from-bottom-1 motion-reduce:animate-none">
      <p className="label-mono px-3 pt-2.5 pb-1 text-[0.68rem] text-ink-faint">{t("chat-mention-executors")}</p>
      <p className="sr-only" aria-live="polite">
        {current ? t("chat-mention-current", { name: current.name, position: active + 1, count: options.length }) : ""}
      </p>
      <ul className="max-h-64 overflow-y-auto p-1">
        {options.map((mention, i) => {
          const brand = brandOf(mention.brand ?? mention.name);
          return (
            <li key={mention.name}>
              <button
                type="button"
                tabIndex={-1}
                // the textarea keeps the focus: choosing with the pointer must not take it
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => onChoose(mention)}
                className={cn(
                  "flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors",
                  i === active ? "bg-paper-sunken" : "hover:bg-paper-sunken/60",
                )}
              >
                <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-md border border-rule bg-paper">
                  {brand ? (
                    <BrandMark brand={brand} className="size-3.5" label={false} />
                  ) : (
                    <span className="font-mono text-[0.7rem] text-ink-muted">@</span>
                  )}
                </span>
                <span className="min-w-0">
                  <span className="block font-mono text-[0.85rem] text-ink">@{mention.name}</span>
                  {mention.description ? (
                    <span className="line-clamp-2 block text-[0.8rem] text-ink-muted">{mention.description}</span>
                  ) : null}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** A message's words, each executor it names as a small tag: its mark and its name, tinted with its colour. */
export function MentionText({ text }: { text: string }): ReactNode {
  const { data: mentions = [] } = useQuery(mentionsQuery);
  if (!mentions.length || !text.includes("@")) return text;
  const known = new Map(mentions.map((m) => [`@${m.name}`, m]));
  return text.split(NAMED).map((part, i) => {
    const mention = known.get(part);
    // biome-ignore lint/suspicious/noArrayIndexKey: the parts of one fixed text
    return mention ? <MentionTag key={i} mention={mention} /> : part;
  });
}

function MentionTag({ mention }: { mention: Mention }) {
  const brand = brandOf(mention.brand ?? mention.name);
  const colour = (brand && brandColour(brand)) ?? "var(--ember)";
  return (
    <span
      className="mx-0.5 inline-flex translate-y-[-1px] items-center gap-1 rounded-md border px-1.5 py-px align-middle text-[0.85em] font-medium text-ink"
      style={{
        backgroundColor: `color-mix(in oklab, ${colour} 14%, transparent)`,
        borderColor: `color-mix(in oklab, ${colour} 32%, transparent)`,
      }}
    >
      {brand ? <BrandMark brand={brand} className="size-3.5" label={false} /> : null}
      {mention.name}
    </span>
  );
}
