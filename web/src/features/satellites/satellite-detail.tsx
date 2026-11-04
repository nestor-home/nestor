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
  "text.input": "sat-means-text-input",
  "text.display": "sat-means-text-display",
  "audio.capture": "sat-means-audio-capture",
  "audio.playback": "sat-means-audio-playback",
  "audio.speech_activity": "sat-means-audio-speech-activity",
  "vision.person_detection": "sat-means-vision-person-detection",
  "expression.emotion": "sat-means-expression-emotion",
  "motion.head": "sat-means-motion-head",
  "device.update": "sat-means-device-update",
};

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
        <dd className="font-mono text-[0.8rem] [overflow-wrap:anywhere]">
          {s.software.name} {s.software.version} · {s.protocol}
        </dd>
      </dl>
      <SoftwareUpdate satellite={s} />
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

/** What the device reported about its software, and the person's way to install a newer version. */
export function SoftwareUpdate({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  const canUpdate = useCan("satellites:write");
  const queryClient = useQueryClient();
  const notify = useNotify();
  const update = useMutation({
    mutationFn: () => api.updateSatellite(s.id),
    onSuccess: (version) => {
      void queryClient.invalidateQueries({ queryKey: keys.satellites });
      notify(t("sat-update-asked", { id: s.name ?? s.id, version }));
    },
  });
  const state = s.update?.state;
  const version = s.update?.version ?? "";
  if (!s.can_update || !state || state === "current") return null;
  return (
    <Section title={t("sat-update")}>
      {state === "installing" ? (
        <Status tone="pending">{t("sat-update-installing", { version })}</Status>
      ) : state === "failed" ? (
        <p role="alert" className="max-w-2xl text-sm text-brick">
          {t("sat-update-failed", { version })}
        </p>
      ) : (
        <div className="grid max-w-2xl gap-4">
          <p className="text-sm text-ink-muted">
            {t("sat-update-available", { version, running: s.software.version })}
          </p>
          {canUpdate && s.connected !== false ? (
            <div>
              <Confirm
                trigger={<Button variant="accent">{t("sat-update-action", { version })}</Button>}
                title={t("sat-update-title", { id: s.name ?? s.id, version })}
                confirm={t("sat-update-confirm")}
                tone="accent"
                onConfirm={() => update.mutateAsync()}
              >
                {t("sat-update-description", { name: s.software.name })}
              </Confirm>
            </div>
          ) : null}
        </div>
      )}
    </Section>
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
