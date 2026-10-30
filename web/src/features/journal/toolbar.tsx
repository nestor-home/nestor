import { CalendarRange, Pause, Play, Search, X } from "lucide-react";
import { forwardRef, useState } from "react";
import { Kbd } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Calendar, calendarLocale, type DateRange } from "@/components/ui/calendar";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
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

export function useRangeLabel(): (from?: string, to?: string) => string {
  const t = useT();
  return (from, to) => {
    if (from && to) return t("jr-range-between", { from: short(from), to: short(to) });
    if (from) return t("jr-range-since", { from: short(from) });
    if (to) return t("jr-range-until", { to: short(to) });
    return t("jr-range-all");
  };
}

export const JournalToolbar = forwardRef<
  HTMLInputElement,
  {
    search: JournalSearch;
    onChange: (next: JournalSearch) => void;
    following: boolean;
    onFollowing: (following: boolean) => void;
  }
>(function JournalToolbar({ search, onChange, following, onFollowing }, searchRef) {
  const t = useT();
  const { locale } = useLocale();
  const rangeLabel = useRangeLabel();
  const [q, setQ] = useState(search.q ?? "");
  const [open, setOpen] = useState(false);
  const range: DateRange | undefined = search.from
    ? { from: new Date(search.from), to: search.to ? new Date(search.to) : undefined }
    : undefined;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <search className="min-w-0 flex-[1_1_18rem]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onChange({ ...search, q: q.trim() || undefined });
          }}
        >
          <label htmlFor="journal-search" className="sr-only">
            {t("jr-search-label")}
          </label>
          <InputGroup>
            <InputGroupAddon>
              <Search aria-hidden="true" />
            </InputGroupAddon>
            <InputGroupInput
              id="journal-search"
              ref={searchRef}
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
                  <X className="size-3.5" />
                </button>
              ) : (
                <Kbd>/</Kbd>
              )}
            </InputGroupAddon>
          </InputGroup>
        </form>
      </search>

      <div className="flex flex-wrap items-center gap-2">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger render={<Button variant="outline" className="max-w-72" />}>
            <CalendarRange aria-hidden="true" />
            <span className="truncate tabular">{rangeLabel(search.from, search.to)}</span>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-auto p-0" aria-label={t("jr-range-label")}>
            <div className="flex flex-col sm:flex-row">
              <ul className="grid content-start gap-0.5 p-2 sm:w-40">
                {PRESETS.map((p) => (
                  <li key={p.id}>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="w-full justify-start"
                      onClick={() => {
                        onChange({ ...search, from: p.span().toISOString(), to: undefined });
                        setOpen(false);
                      }}
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
                    onClick={() => {
                      onChange({ ...search, from: undefined, to: undefined });
                      setOpen(false);
                    }}
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
                  const to = next.to ? new Date(next.to) : undefined;
                  to?.setHours(23, 59, 59, 999);
                  onChange({ ...search, from: startOfDay(next.from).toISOString(), to: to?.toISOString() });
                }}
              />
            </div>
          </PopoverContent>
        </Popover>

        <ToggleGroup
          aria-label={t("jr-density")}
          variant="outline"
          spacing={0}
          value={[search.density ?? "comfortable"]}
          onValueChange={(value: string[]) => {
            const next = value.find((v) => v !== (search.density ?? "comfortable"));
            if (next) onChange({ ...search, density: next === "compact" ? "compact" : undefined });
          }}
        >
          <ToggleGroupItem value="comfortable" className="px-3">
            {t("jr-density-comfortable")}
          </ToggleGroupItem>
          <ToggleGroupItem value="compact" className="px-3">
            {t("jr-density-compact")}
          </ToggleGroupItem>
        </ToggleGroup>

        <Button
          variant={following ? "outline" : "accent"}
          onClick={() => onFollowing(!following)}
          aria-pressed={!following}
          title={t("jr-pause-hint")}
        >
          {following ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
          {following ? t("jr-pause") : t("jr-resume")}
        </Button>
      </div>
    </div>
  );
});
