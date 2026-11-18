import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api, keys, peopleQuery, type Satellite } from "@/api";
import { FormActions } from "@/components/form-actions";
import { useNotify } from "@/components/notices";
import { FormDialog } from "@/components/overlay-form";
import { Fact, Facts, Section } from "@/components/page";
import { FormError, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { isOwner } from "@/features/accounts/rules";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { deviceName } from "@/lib/labels";
import { useCan } from "@/lib/session";
import { draftOf, PrivacyFields, PrivacyRules, privacyOf, privacyProblem } from "./camera-privacy";

const names = (people: { name: string }[]) =>
  people.length ? people.map((p) => p.name).join(", ") : tr("sat-media-owners-only");

/**
 * Who of the household may watch the satellite or call through it, besides its owners, and whether its camera may
 * film: shown to whoever manages satellites, changed in a dialog.
 */
export function MediaAccessSection({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  const manages = useCan("satellites:write");
  const { films, calls } = s;
  if (!manages || !(films || calls)) return null;
  const { access } = s;
  return (
    <Section
      title={t("sat-media-title")}
      aside={
        <FormDialog
          title={t("sat-media-edit-title", { name: deviceName(s) })}
          description={t("sat-media-owners-note")}
          wide
          trigger={
            <Button variant="outline" size="sm">
              {t("sat-media-edit")}
            </Button>
          }
        >
          {(close) => <MediaAccessForm satellite={s} films={films} calls={calls} onDone={close} />}
        </FormDialog>
      }
    >
      <Facts>
        {films ? (
          <Fact term={t("sat-media-camera")}>
            {access.camera ? t("sat-media-camera-on") : t("sat-media-camera-off")}
          </Fact>
        ) : null}
        {films ? (
          <Fact term={t("sat-privacy")}>
            <PrivacyRules privacy={access.privacy} />
          </Fact>
        ) : null}
        {films ? <Fact term={t("sat-media-viewers")}>{names(access.viewers)}</Fact> : null}
        {calls ? <Fact term={t("sat-media-callers")}>{names(access.callers)}</Fact> : null}
      </Facts>
    </Section>
  );
}

function MediaAccessForm({
  satellite: s,
  films,
  calls,
  onDone,
}: {
  satellite: Satellite;
  films: boolean;
  calls: boolean;
  onDone: () => void;
}) {
  const t = useT();
  const people = useQuery(peopleQuery);
  const queryClient = useQueryClient();
  const notify = useNotify();
  const [camera, setCamera] = useState(s.access.camera);
  const [viewers, setViewers] = useState(() => new Set(s.access.viewers.map((p) => p.id)));
  const [callers, setCallers] = useState(() => new Set(s.access.callers.map((p) => p.id)));
  const [privacy, setPrivacy] = useState(() => draftOf(s.access.privacy));
  const [problem, setProblem] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () =>
      api.setMediaAccess(s.id, {
        viewers: [...viewers].sort(),
        callers: [...callers].sort(),
        camera,
        privacy: privacyOf(privacy),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.satellites });
      void queryClient.invalidateQueries({ queryKey: keys.mediaDevices });
      notify(t("sat-media-saved", { name: deviceName(s) }));
      onDone();
    },
  });
  if (people.isPending) return <Loading lines={2} />;
  const everyone = people.data ?? [];
  const household = everyone.filter((p) => !isOwner(p.account));

  function submit(event: FormEvent) {
    event.preventDefault();
    const wrong = films ? privacyProblem(privacy) : null;
    setProblem(wrong);
    if (!wrong) save.mutate();
  }

  const toggle = (set: typeof setViewers, id: string) => (on: boolean) =>
    set((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      {films ? (
        <label htmlFor={`${s.id}-camera`} className="flex items-start justify-between gap-4">
          <span>
            <span className="block text-sm text-ink">{t("sat-media-camera-switch")}</span>
            <span className="block text-xs text-ink-muted">{t("sat-media-camera-hint")}</span>
          </span>
          <Switch id={`${s.id}-camera`} checked={camera} onCheckedChange={setCamera} />
        </label>
      ) : null}
      {household.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("sat-media-nobody")}</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[0.8rem] text-ink-muted">
              <th scope="col" className="py-1.5 font-medium">
                {t("sat-media-person")}
              </th>
              {films ? (
                <th scope="col" className="w-24 py-1.5 text-center font-medium">
                  {t("sat-media-watch")}
                </th>
              ) : null}
              {calls ? (
                <th scope="col" className="w-24 py-1.5 text-center font-medium">
                  {t("sat-media-call")}
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {household.map((p) => (
              <tr key={p.id}>
                <th scope="row" className="py-2 text-left font-normal text-ink">
                  {p.name}
                </th>
                {films ? (
                  <td className="py-2 text-center">
                    <Checkbox
                      aria-label={t("sat-media-watch-for", { name: p.name })}
                      checked={viewers.has(p.id)}
                      disabled={!camera}
                      onCheckedChange={toggle(setViewers, p.id)}
                    />
                  </td>
                ) : null}
                {calls ? (
                  <td className="py-2 text-center">
                    <Checkbox
                      aria-label={t("sat-media-call-for", { name: p.name })}
                      checked={callers.has(p.id)}
                      onCheckedChange={toggle(setCallers, p.id)}
                    />
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {films ? (
        <PrivacyFields
          draft={privacy}
          onChange={(next) => {
            setPrivacy(next);
            setProblem(null);
          }}
          household={everyone}
          disabled={!camera}
        />
      ) : null}
      <FormError error={problem ?? save.error} />
      <FormActions>
        <Button type="submit" disabled={save.isPending}>
          {t("action-save")}
        </Button>
      </FormActions>
    </form>
  );
}
