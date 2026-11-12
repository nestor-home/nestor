/**
 * `@name` in a message: someone of the household, a room, an executor, a connected account. The server reads the
 * names in the text, whatever the channel, loosely (case and accents aside); here they are offered as people type and
 * shown as tags: a person's initial, a room's house, a vendor's mark, with its name.
 */
import { House } from "lucide-react";
import type { ReactNode } from "react";
import type { Mention } from "@/api";
import { useT } from "@/i18n";
import { BrandMark, brandColour, brandOf } from "@/lib/brands";
import { cn } from "@/lib/utils";

export const NAMED = /(?<![\w@])(@[\p{L}\p{N}_-]*[\p{L}\p{N}_])/gu;
const ORDER: Mention["kind"][] = ["person", "room", "executor", "connection"];

/** A name as the server compares it: no case, no accents, words joined by hyphens (`Salle à manger` → `salle-a-manger`). */
export function nameKey(name: string): string {
  const plain = name.toLowerCase().normalize("NFKD").replace(/\p{M}/gu, "").replace(/_/g, "-");
  return (plain.match(/[a-z0-9]+/g) ?? []).join("-");
}

/** What `@query` may name: a handle, or a word of the label, that starts with it. */
export function matching(mentions: Mention[], query: string): Mention[] {
  const typed = nameKey(query);
  return mentions.filter(
    (m) =>
      nameKey(m.handle).startsWith(typed) ||
      nameKey(m.label)
        .split("-")
        .some((w) => w.startsWith(typed)),
  );
}

/** The mention a written `@name` stands for, among `mentions`. */
export function find(mentions: Mention[], written: string): Mention | undefined {
  const key = nameKey(written);
  return mentions.find((m) => nameKey(m.handle) === key) ?? mentions.find((m) => nameKey(m.label) === key);
}

/** What matches, by kind, above the composer. The editor keeps the focus and its arrows move the choice. */
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
  const groups = ORDER.map((kind) => [kind, options.filter((m) => m.kind === kind)] as const).filter(
    ([, items]) => items.length,
  );
  return (
    <div className="absolute right-0 bottom-full left-0 z-30 mb-2 animate-in overflow-hidden rounded-xl border border-rule-strong bg-paper-raised shadow-lg duration-150 fade-in-0 slide-in-from-bottom-1 motion-reduce:animate-none">
      <p className="sr-only" aria-live="polite">
        {current ? t("chat-mention-current", { name: current.label, position: active + 1, count: options.length }) : ""}
      </p>
      <div className="max-h-72 overflow-y-auto p-1">
        {groups.map(([kind, items]) => (
          <section key={kind} className="pb-1">
            <p className="label-mono px-2.5 pt-2 pb-1 text-[0.68rem] text-ink-faint">{t(`chat-mention-${kind}`)}</p>
            <ul>
              {items.map((mention) => {
                const i = options.indexOf(mention);
                return (
                  <li key={`${mention.kind}-${mention.handle}`}>
                    <button
                      type="button"
                      tabIndex={-1}
                      // the editor keeps the focus: choosing with the pointer must not take it
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => onChoose(mention)}
                      className={cn(
                        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left transition-colors",
                        i === active ? "bg-paper-sunken" : "hover:bg-paper-sunken/60",
                      )}
                    >
                      <span className="grid size-6 shrink-0 place-items-center rounded-md border border-rule bg-paper">
                        <MentionMark mention={mention} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-baseline gap-2">
                          <span className="truncate text-[0.88rem] text-ink">{mention.label}</span>
                          <span className="shrink-0 font-mono text-[0.72rem] text-ink-faint">@{mention.handle}</span>
                        </span>
                        {mention.detail ? (
                          <span className="line-clamp-1 block text-[0.78rem] text-ink-muted">{mention.detail}</span>
                        ) : null}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

/** The sign of a mention: a vendor's mark, a room's house, a person's initial. */
function MentionMark({ mention }: { mention: Mention }) {
  const vendor = mention.kind === "executor" || mention.kind === "connection";
  const brand = vendor ? brandOf(mention.brand ?? mention.handle) : null;
  if (brand) return <BrandMark brand={brand} className="size-3.5" label={false} />;
  if (mention.kind === "room") return <House className="size-3.5 text-ink-muted" aria-hidden="true" />;
  return (
    <span className="font-serif text-[0.78rem] leading-none text-ink" aria-hidden="true">
      {mention.label.slice(0, 1).toUpperCase() || "@"}
    </span>
  );
}

/** A message's words, each name it holds that `mentions` knows shown as a tag. */
export function MentionText({ text, mentions }: { text: string; mentions: Mention[] }): ReactNode {
  if (!mentions.length || !text.includes("@")) return text;
  return text.split(NAMED).map((part, i) => {
    const mention = part.startsWith("@") ? find(mentions, part.slice(1)) : undefined;
    // biome-ignore lint/suspicious/noArrayIndexKey: the parts of one fixed text
    return mention ? <MentionTag key={i} mention={mention} /> : part;
  });
}

/** A mention as a tag: its sign and its name, tinted with its vendor's colour (the ember otherwise). */
export function MentionTag({ mention }: { mention: Mention }) {
  const brand = brandOf(mention.brand ?? "");
  const colour = (brand && brandColour(brand)) ?? "var(--ember)";
  return (
    <span
      className="mx-0.5 inline-flex max-w-56 translate-y-[-1px] items-center gap-1 rounded-md border px-1.5 py-px align-middle text-[0.85em] font-medium text-ink"
      style={{
        backgroundColor: `color-mix(in oklab, ${colour} 14%, transparent)`,
        borderColor: `color-mix(in oklab, ${colour} 32%, transparent)`,
      }}
    >
      <MentionMark mention={mention} />
      <span className="truncate">{mention.label}</span>
    </span>
  );
}
