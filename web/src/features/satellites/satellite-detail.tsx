import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Activity, Cpu, Gauge, RadioTower } from "lucide-react";
import type { ReactNode } from "react";
import { api, isMissing, keys, type Satellite, satelliteQuery } from "@/api";
import { Ago } from "@/components/ago";
import { CardHead } from "@/components/card";
import { Confirm } from "@/components/confirm";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { IconTile } from "@/components/marks";
import { useNotify } from "@/components/notices";
import { Fact, Facts, Lead, PageHeader, Panel, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { TabNav } from "@/components/tab-nav";
import { Button } from "@/components/ui/button";
import { ActivityList } from "@/features/journal/activity-list";
import { useT } from "@/i18n";
import { tr } from "@/i18n/runtime";
import { moment } from "@/lib/dates";
import { CAPABILITY_ICON } from "@/lib/icons";
import { deviceName } from "@/lib/labels";
import { personName } from "@/lib/people";
import { useCan, useMe } from "@/lib/session";
import { IdentifyButton } from "./add-satellite";
import { DeviceTile } from "./device-mark";
import { MediaAccessSection } from "./media-access";
import { SatelliteUpdateButton } from "./satellite-update";
import { Connection } from "./satellites-list";

/** What each capability lets the assistant do, said for the household. */
const MEANS: Record<string, string> = {
  "text.input": "sat-means-text-input",
  "text.display": "sat-means-text-display",
  "audio.capture": "sat-means-audio-capture",
  "audio.playback": "sat-means-audio-playback",
  "audio.speech_activity": "sat-means-audio-speech-activity",
  "video.capture": "sat-means-video-capture",
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

/** A satellite's page: the device and its state, what one does with it at once, then its tabs. */
export function SatelliteFrame({ id, children }: { id: string; children: ReactNode }) {
  const t = useT();
  const { satellite: s, pending, error } = useSatellite(id);
  const canPair = useCan("satellites:write");
  const trail: Crumb[] = [
    { label: t("space-settings"), link: { to: "/settings" } },
    { label: t("sat-title"), link: { to: "/satellites" } },
    { label: s ? deviceName(s) : id },
  ];
  if (pending) return <Loading lines={4} />;
  if (error || !s) {
    return (
      <>
        <Crumbs trail={trail} />
        {error ? <Failure error={error} /> : <Empty>{t("sat-unknown")}</Empty>}
      </>
    );
  }
  const base = `/satellites/${s.id}`;
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={
          <span className="flex items-center gap-4">
            <DeviceTile brand={s.brand} capabilities={s.capabilities} className="size-14 rounded-2xl" />
            <span className="min-w-0">{deviceName(s)}</span>
          </span>
        }
        actions={
          <>
            <SatelliteUpdateButton satellite={s} />
            {s.can_identify && s.connected && canPair ? <IdentifyButton device={s.id} /> : null}
          </>
        }
        meta={
          <>
            <Connection satellite={s} />
            {s.name ? <span className="font-mono">{s.id}</span> : null}
            <span>{t("sat-model-room", { model: s.model, room: s.room })}</span>
          </>
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
      <Panel className="grid gap-6">
        <Lead>
          {s.connected
            ? t("sat-summary-connected", { assistant: me.assistant, room: s.room })
            : s.connected === false
              ? t("sat-summary-offline", { room: s.room })
              : t("sat-summary-unknown")}
        </Lead>
        <Facts>
          <Fact term={t("sat-paired-at")}>
            {s.approved_by
              ? t("sat-paired-by", { when: moment(s.paired_at), name: personName(s.approved_by) })
              : moment(s.paired_at)}
          </Fact>
          {s.last_seen_at ? (
            <Fact term={t("sat-last-seen")}>
              <Ago iso={s.last_seen_at} />
            </Fact>
          ) : null}
          <Fact term={t("sat-software")} className="min-w-0 font-mono text-meta">
            {s.software.name} {s.software.version} · {s.protocol}
          </Fact>
        </Facts>
      </Panel>
      <MediaAccessSection satellite={s} />
      {canRevoke ? (
        <Section title={t("sat-revoke")}>
          <div className="surface flex flex-wrap items-center justify-between gap-x-6 gap-y-4 p-5">
            <p className="max-w-xl text-body text-ink-muted">{t("sat-revoke-hint")}</p>
            <Confirm
              trigger={<Button variant="destructive">{t("sat-revoke-action")}</Button>}
              title={t("sat-revoke-title", { id: deviceName(s) })}
              confirm={t("sat-revoke")}
              onConfirm={() => revoke.mutateAsync()}
            >
              {t("sat-revoke-description", { assistant: me.assistant, room: s.room })}
            </Confirm>
          </div>
        </Section>
      ) : null}
    </div>
  );
}

/** What the device was granted, one card each: what it is called and what it lets the assistant do. */
export function SatelliteCapabilities({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  if (s.capabilities.length === 0) return <Empty>{t("sat-capabilities-empty")}</Empty>;
  return (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {s.capabilities.map((c) => (
        <li key={c.name} className="surface p-4">
          <CardHead
            mark={<IconTile icon={CAPABILITY_ICON[c.name] ?? RadioTower} />}
            title={c.label}
            line={means(c.name)}
          >
            <code className="font-mono text-micro text-ink-faint">{c.name}</code>
          </CardHead>
        </li>
      ))}
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
