import { Plus, X } from "lucide-react";
import { useId } from "react";
import type { Day, Privacy, QuietHours } from "@/api";
import { dayValues } from "@/api/schema.gen";
import { Choice } from "@/components/choice";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { TimeInput } from "@/components/ui/time-input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useT } from "@/i18n";
import { activeLocale, tr } from "@/i18n/runtime";
import { weekdayLabel } from "@/lib/labels";

/** A day's short name in the admin's language, which `weekdayLabel` (full names) does not give: 1 January 2024
 *  was a Monday. */
const shortDay = (day: Day) =>
  new Intl.DateTimeFormat(activeLocale(), { weekday: "short" }).format(new Date(2024, 0, 1 + dayValues.indexOf(day)));

/** One slot in a line: its days, then its times (the whole day when both are equal). */
function slotText(slot: QuietHours): string {
  const days = slot.days.length === 7 ? tr("sat-privacy-every-day") : slot.days.map(shortDay).join(", ");
  return slot.start === slot.end
    ? tr("sat-privacy-quiet-day", { days })
    : tr("sat-privacy-quiet", { days, start: slot.start, end: slot.end });
}

/** The device's privacy rules, one per line; "no rule" said plainly when there are none. */
export function PrivacyRules({ privacy }: { privacy: Privacy }) {
  const t = useT();
  const lines = privacy.quiet.map(slotText);
  if (privacy.off_when_home) {
    const people = new Intl.ListFormat(activeLocale(), { type: "disjunction" }).format(
      privacy.home_people.map((p) => p.name),
    );
    lines.push(privacy.home_people.length ? t("sat-privacy-home-people", { people }) : t("sat-privacy-home-anyone"));
  }
  if (!lines.length) return <>{t("sat-privacy-none")}</>;
  return (
    <ul className="grid gap-0.5">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

/** A quiet-hours slot being edited, keyed for React. */
export interface SlotDraft extends QuietHours {
  key: number;
}

/** The privacy rules as the form edits them. */
export interface PrivacyDraft {
  quiet: SlotDraft[];
  offWhenHome: boolean;
  some: boolean; // only the ticked people count, else anyone of the household
  people: Set<string>;
}

let nextKey = 0;
export const draftOf = (privacy: Privacy): PrivacyDraft => ({
  quiet: privacy.quiet.map((q) => ({ ...q, key: nextKey++ })),
  offWhenHome: privacy.off_when_home,
  some: privacy.home_people.length > 0,
  people: new Set(privacy.home_people.map((p) => p.id)),
});

/** What the server takes; days in order (Monday first), the people only when they are chosen. */
export const privacyOf = (draft: PrivacyDraft) => ({
  quiet: draft.quiet.map(({ days, start, end }) => ({ days: dayValues.filter((d) => days.includes(d)), start, end })),
  off_when_home: draft.offWhenHome,
  home_people: draft.offWhenHome && draft.some ? [...draft.people].sort() : [],
});

/** Why the draft cannot be sent yet, if it cannot: a slot without a day, or no one picked among some people. */
export function privacyProblem(draft: PrivacyDraft): string | null {
  if (draft.quiet.some((q) => !q.days.length)) return tr("sat-privacy-no-day");
  if (draft.offWhenHome && draft.some && !draft.people.size) return tr("sat-privacy-no-person");
  return null;
}

/** When the camera does not film: quiet-hours slots, and off while someone is home. */
export function PrivacyFields({
  draft,
  onChange,
  household,
  disabled,
}: {
  draft: PrivacyDraft;
  onChange: (draft: PrivacyDraft) => void;
  household: { id: string; name: string }[];
  disabled: boolean;
}) {
  const t = useT();
  const id = useId();
  const setSlot = (key: number, change: Partial<QuietHours>) =>
    onChange({ ...draft, quiet: draft.quiet.map((q) => (q.key === key ? { ...q, ...change } : q)) });
  const add = () =>
    onChange({
      ...draft,
      quiet: [...draft.quiet, { key: nextKey++, days: [...dayValues], start: "22:00", end: "07:00" }],
    });
  const remove = (key: number) => onChange({ ...draft, quiet: draft.quiet.filter((q) => q.key !== key) });
  const tick = (person: string) => (on: boolean) => {
    const people = new Set(draft.people);
    if (on) people.add(person);
    else people.delete(person);
    onChange({ ...draft, people });
  };

  return (
    <fieldset className="grid gap-4" disabled={disabled}>
      <legend className="mb-1 text-meta font-medium text-ink">{t("sat-privacy-title")}</legend>
      <p className="-mt-2 text-micro text-ink-muted">{t("sat-privacy-calls")}</p>
      {draft.quiet.length === 0 && !draft.offWhenHome ? (
        <p className="text-meta text-ink-muted">{t("sat-privacy-none")}</p>
      ) : null}
      {draft.quiet.map((slot, index) => (
        <fieldset key={slot.key} className="grid gap-3 rounded-lg border border-rule p-3">
          <legend className="sr-only">{t("sat-privacy-slot", { n: index + 1 })}</legend>
          <div className="flex items-start justify-between gap-2">
            <ToggleGroup
              multiple
              variant="outline"
              size="sm"
              spacing={1}
              className="flex-wrap"
              aria-label={t("sat-privacy-days")}
              value={slot.days}
              onValueChange={(days) => setSlot(slot.key, { days: days as Day[] })}
            >
              {dayValues.map((day) => (
                <ToggleGroupItem key={day} value={day} aria-label={weekdayLabel(day)}>
                  {shortDay(day)}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t("sat-privacy-remove", { n: index + 1 })}
              onClick={() => remove(slot.key)}
            >
              <X />
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-meta">
            <Label htmlFor={`${id}-${slot.key}-start`}>{t("sat-privacy-from")}</Label>
            <TimeInput
              id={`${id}-${slot.key}-start`}
              value={slot.start}
              required
              onChange={(e) => e.target.value && setSlot(slot.key, { start: e.target.value.slice(0, 5) })}
            />
            <Label htmlFor={`${id}-${slot.key}-end`}>{t("sat-privacy-to")}</Label>
            <TimeInput
              id={`${id}-${slot.key}-end`}
              value={slot.end}
              required
              onChange={(e) => e.target.value && setSlot(slot.key, { end: e.target.value.slice(0, 5) })}
            />
          </div>
        </fieldset>
      ))}
      <div className="grid gap-1.5">
        <Button type="button" variant="outline" size="sm" className="w-fit" onClick={add}>
          <Plus /> {t("sat-privacy-add")}
        </Button>
        {draft.quiet.length ? <p className="text-micro text-ink-muted">{t("sat-privacy-slot-hint")}</p> : null}
      </div>
      <label htmlFor={`${id}-home`} className="flex items-start justify-between gap-4">
        <span>
          <span className="block text-meta text-ink">{t("sat-privacy-home")}</span>
          <span className="block text-micro text-ink-muted">{t("sat-privacy-home-hint")}</span>
        </span>
        <Switch
          id={`${id}-home`}
          checked={draft.offWhenHome}
          disabled={disabled}
          onCheckedChange={(offWhenHome) => onChange({ ...draft, offWhenHome })}
        />
      </label>
      {draft.offWhenHome ? (
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor={`${id}-who`} className="text-meta font-medium text-ink">
              {t("sat-privacy-who")}
            </Label>
            <Choice
              id={`${id}-who`}
              value={draft.some ? "some" : "anyone"}
              disabled={disabled}
              options={[
                { value: "anyone", label: t("sat-privacy-who-anyone") },
                { value: "some", label: t("sat-privacy-who-some") },
              ]}
              onChange={(who) => onChange({ ...draft, some: who === "some" })}
            />
          </div>
          {draft.some ? (
            <ul className="grid gap-2 sm:grid-cols-2">
              {household.map((p) => (
                <li key={p.id}>
                  <Label className="flex items-center gap-2 text-meta font-normal text-ink">
                    <Checkbox checked={draft.people.has(p.id)} disabled={disabled} onCheckedChange={tick(p.id)} />
                    {p.name}
                  </Label>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </fieldset>
  );
}
