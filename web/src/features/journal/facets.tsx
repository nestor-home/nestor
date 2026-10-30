import { Check, ChevronDown, SlidersHorizontal, X } from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import type { Facet, JournalFacets } from "@/api";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useT } from "@/i18n";
import { KindMark } from "@/lib/brands";
import { kindStyle } from "@/lib/icons";
import { number } from "@/lib/time";
import { cn } from "@/lib/utils";
import type { JournalSearch } from "./search";

/**
 * The journal's facets as one row of filter buttons (shadcn's faceted filter: a Popover with a
 * searchable Command list). Each value shows its count for the other filters as they are.
 * Kinds combine; person, channel and room pick one.
 */
/** Filters that come from a link elsewhere (a task's page, a connection's activity…), shown so they can be removed. */
const SUBJECTS = ["session", "conversation", "task", "watch", "connection", "satellite", "tone"] as const;

interface Group {
  id: "kinds" | "person" | "channel" | "room";
  label: string;
  facets: Facet[] | undefined;
  selected: string[];
  multiple: boolean;
  render?: (facet: Facet) => ReactNode;
  onChange: (value: string[]) => void;
}

function useGroups(
  facets: JournalFacets | undefined,
  search: JournalSearch,
  onChange: (next: JournalSearch) => void,
): Group[] {
  const t = useT();
  const kinds = search.kinds?.split(",") ?? [];
  return [
    {
      id: "kinds",
      label: t("jr-facet-kind"),
      facets: facets?.kinds,
      selected: kinds,
      multiple: true,
      render: (f) => {
        const style = kindStyle(f.key);
        return <style.icon className={cn("size-3.5", style.tone)} aria-hidden="true" />;
      },
      onChange: (value) => onChange({ ...search, kinds: value.length ? value.join(",") : undefined }),
    },
    {
      id: "person",
      label: t("jr-facet-person"),
      facets: facets?.people,
      selected: search.person ? [search.person] : [],
      multiple: false,
      onChange: (value) => onChange({ ...search, person: value[0] }),
    },
    {
      id: "channel",
      label: t("jr-facet-channel"),
      facets: facets?.channels,
      selected: search.channel ? [search.channel] : [],
      multiple: false,
      render: (f) => <KindMark kind={f.key} className="size-3.5" label={false} />,
      onChange: (value) => onChange({ ...search, channel: value[0] }),
    },
    {
      id: "room",
      label: t("jr-facet-room"),
      facets: facets?.rooms,
      selected: search.room ? [search.room] : [],
      multiple: false,
      onChange: (value) => onChange({ ...search, room: value[0] }),
    },
  ];
}

const cleared = (search: JournalSearch): JournalSearch => ({
  ...search,
  kinds: undefined,
  person: undefined,
  channel: undefined,
  room: undefined,
});

/** Filters arriving from a link (a task, a connection…): shown as chips that remove themselves. */
function SubjectChips({ search, onChange }: { search: JournalSearch; onChange: (next: JournalSearch) => void }) {
  const t = useT();
  return SUBJECTS.filter((key) => search[key]).map((key) => (
    <Button
      key={key}
      variant="outline"
      size="sm"
      className="max-w-full border-ink"
      onClick={() => onChange({ ...search, [key]: undefined })}
      aria-label={t("jr-subject-remove", { subject: t(`jr-subject-${key}`), id: search[key] ?? "" })}
    >
      {t(`jr-subject-${key}`)}
      <span className="truncate font-mono text-[0.7rem] font-normal">{search[key]}</span>
      <X className="text-ink-faint" aria-hidden="true" />
    </Button>
  ));
}

export function FilterBar({
  facets,
  search,
  onChange,
}: {
  facets: JournalFacets | undefined;
  search: JournalSearch;
  onChange: (next: JournalSearch) => void;
}) {
  const t = useT();
  const groups = useGroups(facets, search, onChange);
  const active = groups.reduce((n, g) => n + g.selected.length, 0);
  return (
    <div className="flex flex-wrap items-center gap-2">
      {groups.map((g) => (
        <FacetFilter key={g.id} {...g} />
      ))}
      <SubjectChips search={search} onChange={onChange} />
      {active ? (
        <Button variant="ghost" size="sm" onClick={() => onChange(cleared(search))}>
          <X aria-hidden="true" />
          {t("jr-facet-clear")}
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Below `md`: one "Filtres" button opening a bottom sheet with the same facets as large rows,
 * and the chosen values kept visible above the stream as chips that remove themselves.
 */
export function FilterSheet({
  facets,
  search,
  onChange,
}: {
  facets: JournalFacets | undefined;
  search: JournalSearch;
  onChange: (next: JournalSearch) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const groups = useGroups(facets, search, onChange);
  const chosen = groups.flatMap((g) =>
    (g.facets ?? []).filter((f) => g.selected.includes(f.key)).map((f) => ({ group: g, facet: f })),
  );
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger render={<Button variant="outline" />}>
          <SlidersHorizontal aria-hidden="true" />
          {t("jr-filters")}
          {chosen.length ? <span className="font-mono text-[0.72rem]">{chosen.length}</span> : null}
        </SheetTrigger>
        <SheetContent
          side="bottom"
          className="max-h-[85dvh] overflow-y-auto overscroll-contain rounded-t-xl bg-paper pb-[env(safe-area-inset-bottom)]"
        >
          <SheetHeader className="border-b border-rule px-5 pt-5 pb-3">
            <SheetTitle className="font-serif text-xl font-normal">{t("jr-filters")}</SheetTitle>
          </SheetHeader>
          <div className="grid gap-6 px-5 pb-6">
            {groups.map((g) =>
              g.facets?.length ? (
                <section key={g.id} aria-labelledby={`sheet-${g.id}`}>
                  <h3 id={`sheet-${g.id}`} className="label-mono mb-1.5">
                    {g.label}
                  </h3>
                  <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
                    {g.facets.map((f) => {
                      const on = g.selected.includes(f.key);
                      return (
                        <li key={f.key}>
                          <button
                            type="button"
                            aria-pressed={on}
                            onClick={() =>
                              g.onChange(
                                g.multiple
                                  ? on
                                    ? g.selected.filter((k) => k !== f.key)
                                    : [...g.selected, f.key]
                                  : on
                                    ? []
                                    : [f.key],
                              )
                            }
                            className="flex min-h-11 w-full items-center gap-3 px-4 text-left text-sm aria-pressed:bg-paper-sunken"
                          >
                            <span
                              aria-hidden="true"
                              className={cn(
                                "grid size-4 place-items-center rounded-sm border border-rule-strong",
                                on && "border-ink bg-ink text-paper",
                              )}
                            >
                              {on ? <Check className="size-3" /> : null}
                            </span>
                            {g.render?.(f)}
                            <span className="flex-1 truncate">{f.label}</span>
                            <span className="font-mono text-[0.72rem] text-ink-faint tabular">{number(f.count)}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ) : null,
            )}
            <div className="sticky bottom-0 -mx-5 flex gap-2 border-t border-rule bg-paper px-5 pt-3 pb-3">
              <Button
                variant="ghost"
                className="flex-1"
                onClick={() => onChange(cleared(search))}
                disabled={!chosen.length}
              >
                {t("jr-facet-clear")}
              </Button>
              <Button className="flex-1" onClick={() => setOpen(false)}>
                {t("jr-filters-show")}
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
      {chosen.map(({ group, facet }) => (
        <Button
          key={`${group.id}-${facet.key}`}
          variant="outline"
          size="sm"
          className="border-ink"
          onClick={() => group.onChange(group.selected.filter((k) => k !== facet.key))}
          aria-label={t("jr-chip-remove", { value: facet.label })}
        >
          {group.render?.(facet)}
          {facet.label}
          <X className="text-ink-faint" aria-hidden="true" />
        </Button>
      ))}
      <SubjectChips search={search} onChange={onChange} />
    </div>
  );
}

function FacetFilter({
  label,
  facets,
  selected,
  multiple = false,
  render,
  onChange,
}: {
  label: string;
  facets: Facet[] | undefined;
  selected: string[];
  multiple?: boolean;
  render?: (facet: Facet) => ReactNode;
  onChange: (value: string[]) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const chosen = (facets ?? []).filter((f) => selected.includes(f.key));
  const toggle = (key: string) => {
    if (multiple) onChange(selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key]);
    else {
      onChange(selected.includes(key) ? [] : [key]);
      setOpen(false);
    }
  };
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className={cn("border-dashed", selected.length && "border-solid border-ink")}
          />
        }
      >
        {label}
        {chosen.length ? (
          <span className="flex items-center gap-1 font-normal">
            {chosen.length > 2 ? (
              <span className="font-mono text-[0.7rem]">{t("jr-facet-selected", { count: chosen.length })}</span>
            ) : (
              chosen.map((f) => (
                <span key={f.key} className="rounded-sm bg-paper-sunken px-1.5 font-mono text-[0.7rem]">
                  {f.label}
                </span>
              ))
            )}
          </span>
        ) : null}
        <ChevronDown className="text-ink-faint" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-0" aria-label={label}>
        <Command>
          <CommandInput placeholder={t("jr-facet-search", { facet: label })} />
          <CommandList>
            <CommandEmpty>{t("jr-facet-empty")}</CommandEmpty>
            <CommandGroup>
              {(facets ?? []).map((f) => {
                const on = selected.includes(f.key);
                return (
                  <CommandItem key={f.key} value={`${f.label} ${f.key}`} onSelect={() => toggle(f.key)}>
                    <span
                      aria-hidden="true"
                      className={cn(
                        "grid size-3.5 place-items-center rounded-sm border border-rule-strong",
                        on && "border-ink bg-ink text-paper",
                      )}
                    >
                      {on ? <Check className="size-2.5" /> : null}
                    </span>
                    {render?.(f)}
                    <span className="flex-1 truncate">{f.label}</span>
                    <span className="font-mono text-[0.7rem] text-ink-faint tabular">{number(f.count)}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
