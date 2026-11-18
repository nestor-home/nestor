import { CalendarRange, Search, X } from "lucide-react";
import { type Ref, useState } from "react";
import { Kbd } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Calendar, calendarLocale, type DateRange } from "@/components/ui/calendar";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLocale, useT } from "@/i18n";
import { activeLocale } from "@/i18n/runtime";
import type { JournalSearch } from "./search";

const HOUR = 3600_000;

const PRESETS: { id: string; span: () => Date }[] = [
  { id: "jr-range-hour", span: () => new Date(Date.now() - HOUR) },
  { id: "jr-range-today", span: () => startOfDay(new Date()) },
  { id: "jr-range-day", span: () => new Date(Date.now() - 24 * HOUR) },
  { id: "jr-range-week", span: () => new Date(Date.now() - 7 * 24 * HOUR) },
];

function startOfDay(d: Date): Date {
  const copy = new Date(d);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

const short = (iso: string) =>
  new Intl.DateTimeFormat(activeLocale(), {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));

interface Props {
  search: JournalSearch;
  onChange: (next: JournalSearch) => void;
}

/** The words to look for in the journal; Enter searches, `/` comes here from anywhere on the page. */
export function SearchField({ search, onChange, ref }: Props & { ref: Ref<HTMLInputElement> }) {
  const t = useT();
  const [q, setQ] = useState(search.q ?? "");
  return (
    <search className="min-w-0 flex-[1_1_16rem]">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onChange({ ...search, q: q.trim() || undefined });
        }}
      >
        <label htmlFor="journal-search" className="sr-only">
          {t("jr-search-label")}
        </label>
        <InputGroup className="h-11 rounded-full border-transparent px-1.5 shadow-(--lift)">
          <InputGroupAddon>
            <Search aria-hidden="true" />
          </InputGroupAddon>
          <InputGroupInput
            id="journal-search"
            ref={ref}
            type="search"
            placeholder={t("jr-search-placeholder")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            spellCheck={false}
          />
          <InputGroupAddon align="inline-end">
            {search.q ? (
              <button
                type="button"
                aria-label={t("jr-search-clear")}
                className="text-ink-faint hover:text-ink"
                onClick={() => {
                  setQ("");
                  onChange({ ...search, q: undefined });
                }}
              >
                <X className="size-4" />
              </button>
            ) : (
              <span className="hidden md:inline-flex">
                <Kbd>/</Kbd>
              </span>
            )}
          </InputGroupAddon>
        </InputGroup>
      </form>
    </search>
  );
}

/** The period the journal shows: a few usual spans, or days picked on the calendar. */
export function PeriodPicker({ search, onChange }: Props) {
  const t = useT();
  const { locale } = useLocale();
  const [open, setOpen] = useState(false);
  const { from, to } = search;
  const label =
    from && to
      ? t("jr-range-between", { from: short(from), to: short(to) })
      : from
        ? t("jr-range-since", { from: short(from) })
        : to
          ? t("jr-range-until", { to: short(to) })
          : t("jr-range-all");
  const range: DateRange | undefined = from ? { from: new Date(from), to: to ? new Date(to) : undefined } : undefined;
  const pick = (next: Pick<JournalSearch, "from" | "to">) => {
    onChange({ ...search, ...next });
    setOpen(false);
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={<Button variant="pill" className="h-11 max-w-full px-4" />}>
        <CalendarRange aria-hidden="true" />
        <span className="truncate tabular">{label}</span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-auto max-w-[calc(100vw-2rem)] p-0" aria-label={t("jr-range-label")}>
        <div className="flex flex-col sm:flex-row">
          <ul className="flex flex-wrap gap-1 p-2 sm:grid sm:w-40 sm:content-start sm:gap-0.5">
            {PRESETS.map((p) => (
              <li key={p.id}>
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full justify-start"
                  onClick={() => pick({ from: p.span().toISOString(), to: undefined })}
                >
                  {t(p.id)}
                </Button>
              </li>
            ))}
            <li>
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start"
                onClick={() => pick({ from: undefined, to: undefined })}
              >
                {t("jr-range-all")}
              </Button>
            </li>
          </ul>
          <div aria-hidden="true" className="h-px bg-rule sm:h-auto sm:w-px" />
          <Calendar
            mode="range"
            locale={calendarLocale(locale)}
            selected={range}
            disabled={{ after: new Date() }}
            onSelect={(next) => {
              if (!next?.from) return;
              const end = next.to ? new Date(next.to) : undefined;
              end?.setHours(23, 59, 59, 999);
              onChange({ ...search, from: startOfDay(next.from).toISOString(), to: end?.toISOString() });
            }}
          />
        </div>
      </PopoverContent>
    </Popover>
  );
}
