import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Activity, Cpu, Gauge } from "lucide-react";
import type { ReactNode } from "react";
import { api, isMissing, keys, type Satellite, satelliteQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Confirm } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { useNotify } from "@/components/notices";
import { PageHeader, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { TabNav } from "@/components/tab-nav";
import { Button } from "@/components/ui/button";
import { ActivityList } from "@/features/journal/activity-list";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { BrandMark, brandOf } from "@/lib/brands";
import { moment } from "@/lib/dates";
import { CAPABILITY_ICON } from "@/lib/icons";
import { usePeopleNames } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { IdentifyButton } from "./add-satellite";

/** What each capability lets the assistant do, said for the household. */
const MEANS: Record<string, string> = {
  "audio.capture": "sat-means-audio-capture",
  "audio.playback": "sat-means-audio-playback",
  "audio.speech_activity": "sat-means-audio-speech-activity",
  "vision.person_detection": "sat-means-vision-person-detection",
  "expression.emotion": "sat-means-expression-emotion",
  "motion.head": "sat-means-motion-head",
};

/** The wire format satellites speak: an identifier, not language. */
const PROTOCOL = "nestor.satellite/2";

function means(capability: string): string | null {
  const id = MEANS[capability];
  return id ? tr(id) : null;
}

export function useSatellite(id: string): { satellite: Satellite | undefined; pending: boolean; error: unknown } {
  const found = useQuery(satelliteQuery(id));
  return { satellite: found.data, pending: found.isPending, error: isMissing(found.error) ? null : found.error };
}

export function SatelliteFrame({ id, children }: { id: string; children: ReactNode }) {
  const t = useT();
  const { satellite: s, pending, error } = useSatellite(id);
  const canPair = useCan("satellites:write");
  const trail: Crumb[] = [{ label: t("sat-title"), link: { to: "/satellites" } }, { label: id }];
  if (pending) return <Loading lines={4} />;
  if (error || !s) {
    return (
      <>
        <Crumbs trail={trail} />
        {error ? <Failure error={error} /> : <Empty>{t("sat-unknown")}</Empty>}
      </>
    );
  }
  const brand = brandOf(s.brand);
  const base = `/satellites/${s.id}`;
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={
          <span className="inline-flex items-center gap-3">
            {brand ? <BrandMark brand={brand} className="size-7 text-ink" /> : null}
            {s.name ?? <span className="font-mono text-[2rem] tracking-tight">{s.id}</span>}
          </span>
        }
        actions={s.can_identify && s.connected && canPair ? <IdentifyButton device={s.id} /> : undefined}
        meta={
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.85rem] text-ink-muted">
            {s.connected === null ? null : s.connected ? (
              <Status tone="ok">{t("sat-state-connected")}</Status>
            ) : (
              <Status tone="attention">{t("sat-state-offline")}</Status>
            )}
            {s.name ? <span className="font-mono">{s.id}</span> : null}
            <span>{s.model}</span>
            <span>{t("sat-room", { room: s.room })}</span>
          </p>
        }
      />
      <TabNav
        label={t("sat-tabs")}
        tabs={[
          { to: base, label: t("sat-tab-overview"), icon: Gauge },
          { to: `${base}/capabilities`, label: t("sat-tab-capabilities"), icon: Cpu, count: s.capabilities.length },
          { to: `${base}/activity`, label: t("sat-tab-activity"), icon: Activity },
        ]}
      />
      {children}
    </>
  );
}

export function SatelliteOverview({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  const me = useMe();
  const name = usePeopleNames();
  const canRevoke = useCan("satellites:write");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const notify = useNotify();
  const revoke = useMutation({
    mutationFn: () => api.revoke(s.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.satellites });
      notify(t("sat-revoked-notice", { id: s.id }));
      void navigate({ to: "/satellites" });
    },
  });
  const sdk = brandOf(s.sdk);
  return (
    <div className="grid gap-10">
      <p className="max-w-2xl font-serif text-[1.2rem] leading-relaxed text-pretty [font-variation-settings:'opsz'_20]">
        {s.connected
          ? t("sat-summary-connected", { assistant: me.assistant, room: s.room })
          : s.connected === false
            ? t("sat-summary-offline", { room: s.room })
            : t("sat-summary-unknown")}
      </p>
      <dl className="grid max-w-2xl grid-cols-1 gap-x-6 sm:grid-cols-[10rem_1fr] gap-y-2.5 text-sm">
        <dt className="label-mono pt-0.5">{t("sat-paired-at")}</dt>
        <dd>
          {s.approved_by
            ? t("sat-paired-by", { when: moment(s.paired_at), name: name(s.approved_by) })
            : moment(s.paired_at)}
        </dd>
        <dt className="label-mono pt-0.5">{t("sat-last-seen")}</dt>
        <dd>{s.last_seen_at ? <Ago iso={s.last_seen_at} /> : "—"}</dd>
        <dt className="label-mono pt-0.5">{t("sat-software")}</dt>
        <dd className="flex items-center gap-2 font-mono text-[0.8rem]">
          {sdk ? <BrandMark brand={sdk} className="size-3.5" /> : null}
          {s.sdk ? t("sat-sdk", { sdk: s.sdk, version: s.sdk_version ?? "" }) : t("sat-sdk-unknown")} · {PROTOCOL}
        </dd>
      </dl>
      {canRevoke ? (
        <Section title={t("sat-revoke")}>
          <p className="mb-4 max-w-2xl text-sm text-ink-muted">{t("sat-revoke-hint")}</p>
          <Confirm
            trigger={<Button variant="destructive">{t("sat-revoke-action")}</Button>}
            title={t("sat-revoke-title", { id: s.id })}
            confirm={t("sat-revoke")}
            onConfirm={() => revoke.mutateAsync()}
          >
            {t("sat-revoke-description", { assistant: me.assistant, room: s.room })}
          </Confirm>
        </Section>
      ) : null}
    </div>
  );
}

export function SatelliteCapabilities({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  if (s.capabilities.length === 0) return <Empty>{t("sat-capabilities-empty")}</Empty>;
  return (
    <ul className="grid max-w-3xl gap-px overflow-hidden rounded-md border border-rule bg-rule">
      {s.capabilities.map((c) => {
        const Icon = CAPABILITY_ICON[c.name];
        return (
          <li key={c.name} className="grid grid-cols-[1.5rem_1fr] gap-x-3 bg-paper-raised px-4 py-3">
            {Icon ? <Icon className="mt-0.5 size-4 text-ink" aria-hidden="true" /> : <span />}
            <div>
              <p className="flex flex-wrap items-baseline gap-x-3">
                <span className="text-ink">{c.label}</span>
                <code className="text-[0.7rem] text-ink-faint">{c.name}</code>
              </p>
              {means(c.name) ? <p className="mt-0.5 text-sm text-ink-muted">{means(c.name)}</p> : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function SatelliteActivity({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  return (
    <ActivityList
      filters={{ satellite: s.id }}
      search={{ satellite: s.id }}
      limit={20}
      empty={t("sat-activity-empty")}
    />
  );
}
