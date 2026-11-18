import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CircleArrowUp } from "lucide-react";
import { type Addition, api, keys, messageOf, type PairingRequest, type Satellite, satellitesQuery } from "@/api";
import { Ago } from "@/components/ago";
import { type Crumb, Crumbs } from "@/components/crumbs";
import { useNotify } from "@/components/notices";
import { FormDialog } from "@/components/overlay-form";
import { PageHeader, RowList, Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import { remaining } from "@/lib/dates";
import { deviceName } from "@/lib/labels";
import { useCan, useMe } from "@/lib/session";
import { AddSatelliteButton, IdentifyButton } from "./add-satellite";
import { ApproveForm } from "./approve-form";
import { CapabilityMarks, DeviceTile } from "./device-mark";

/**
 * "Satellites": the devices the agent hears, speaks and sees through. Those asking to pair come first, with
 * what to do; then the additions under way; then every paired device as a card that leads to its page.
 */
export function SatellitesView({
  approving,
  onApprove,
}: {
  approving?: string;
  onApprove: (id: string | undefined) => void;
}) {
  const t = useT();
  const me = useMe();
  const canPair = useCan("satellites:write");
  const trail: Crumb[] = [{ label: t("space-settings"), link: { to: "/settings" } }, { label: t("sat-title") }];
  return (
    <>
      <PageHeader
        crumbs={<Crumbs trail={trail} />}
        title={t("sat-title")}
        actions={canPair ? <AddSatelliteButton /> : undefined}
      >
        {t("sat-lede", { assistant: me.assistant })}
      </PageHeader>
      <Devices approving={approving} onApprove={onApprove} />
    </>
  );
}

function Devices({ approving, onApprove }: { approving?: string; onApprove: (id: string | undefined) => void }) {
  const t = useT();
  const satellites = useQuery(satellitesQuery);
  if (satellites.isPending) return <Loading lines={3} />;
  if (satellites.isError) return <Failure error={satellites.error} retry={() => void satellites.refetch()} />;
  const { pending, paired, additions } = satellites.data;
  const request = pending.find((p) => p.pairing_id === approving);
  return (
    <div className="grid gap-10">
      {pending.length ? (
        <Pending requests={pending} receivedAt={satellites.dataUpdatedAt} onApprove={onApprove} />
      ) : null}
      {additions.length ? <Additions additions={additions} /> : null}
      <Section title={t("sat-paired")} count={paired.length}>
        {paired.length === 0 ? (
          <Empty hint={t("sat-paired-empty-hint")}>{t("sat-paired-empty")}</Empty>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {paired.map((s) => (
              <PairedCard key={s.id} satellite={s} />
            ))}
          </ul>
        )}
      </Section>
      <ApproveDialog request={request} onClose={() => onApprove(undefined)} />
    </div>
  );
}

/** Devices that asked to pair: what each is, how long its request holds, and what to do with it. */
function Pending({
  requests,
  receivedAt,
  onApprove,
}: {
  requests: PairingRequest[];
  receivedAt: number;
  onApprove: (id: string) => void;
}) {
  const t = useT();
  const canPair = useCan("satellites:write");
  const now = useNow();
  return (
    <Section title={t("sat-pending")} count={requests.length}>
      <ul className="grid gap-3 sm:grid-cols-2">
        {requests.map((r) => (
          <li key={r.pairing_id} className="surface flex flex-col gap-4 p-5">
            <div className="flex items-start gap-3.5">
              <DeviceTile brand={r.device.brand} capabilities={r.capabilities} className="bg-amber-soft text-amber" />
              <div className="min-w-0 flex-1">
                <h3 className="font-mono text-[0.95rem] font-medium [overflow-wrap:anywhere] text-ink">
                  {r.device.id}
                </h3>
                <p className="text-[0.92rem] text-ink-muted">
                  {t("sat-model-room", { model: r.device.model, room: r.device.room })}
                </p>
              </div>
            </div>
            <p className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <Status tone="pending">
                <span className="tabular">
                  {t("sat-expires-in", { remaining: remaining(receivedAt + r.expires_in_s * 1000, now) })}
                </span>
              </Status>
              <CapabilityMarks capabilities={r.capabilities} />
            </p>
            <p className="text-[0.95rem] text-ink">{r.methods.find((m) => m.id === r.recommended_method)?.hint}</p>
            {canPair ? (
              <div className="mt-auto flex flex-wrap gap-2">
                <Button size="sm" onClick={() => onApprove(r.pairing_id)}>
                  {t("sat-approve")}
                </Button>
                {r.can_identify ? <IdentifyButton pairing={r.pairing_id} /> : null}
              </div>
            ) : (
              <p className="mt-auto text-[0.92rem] text-ink-muted">{t("sat-approve-forbidden")}</p>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function ApproveDialog({ request, onClose }: { request: PairingRequest | undefined; onClose: () => void }) {
  const t = useT();
  const me = useMe();
  return (
    <FormDialog
      open={Boolean(request)}
      onOpenChange={(open) => !open && onClose()}
      wide
      title={t("sat-approve-title", { id: request?.device.id ?? "" })}
      description={t("sat-approve-description", { assistant: me.assistant, room: request?.device.room ?? "" })}
    >
      {() => (request ? <ApproveForm request={request} onDone={onClose} /> : null)}
    </FormDialog>
  );
}

/** A paired device: what it is, where, whether it answers, what it can do, and an update that waits. */
function PairedCard({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  return (
    <li>
      <Link
        to="/satellites/$satelliteId"
        params={{ satelliteId: s.id }}
        className="surface flex h-full flex-col gap-4 p-5"
      >
        <span className="flex items-start justify-between gap-3">
          <DeviceTile brand={s.brand} capabilities={s.capabilities} />
          <span className="pt-1 text-right">
            <Connection satellite={s} />
          </span>
        </span>
        <span className="min-w-0">
          <span className="block font-serif text-[1.35rem] leading-tight [overflow-wrap:anywhere] text-ink">
            {deviceName(s)}
          </span>
          <span className="mt-1 block text-[0.95rem] text-ink-muted">
            {t("sat-model-room", { model: s.model, room: s.room })}
          </span>
        </span>
        <span className="mt-auto flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-rule pt-3">
          <CapabilityMarks capabilities={s.capabilities} />
          {s.update?.state === "available" ? (
            <span className="inline-flex items-center gap-1.5 text-[0.85rem] font-medium text-ember">
              <CircleArrowUp className="size-3.5" aria-hidden="true" />
              {t("sat-update-badge")}
            </span>
          ) : null}
        </span>
      </Link>
    </li>
  );
}

/** Whether the device answers, and since when it does not. */
export function Connection({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  if (s.connected === null) return <Status tone="idle">{t("sat-state-unknown")}</Status>;
  if (s.connected) return <Status tone="ok">{t("sat-state-connected")}</Status>;
  return (
    <Status tone="attention">
      {t("sat-state-offline")}
      {s.last_seen_at ? (
        <>
          {" · "}
          <Ago iso={s.last_seen_at} />
        </>
      ) : null}
    </Status>
  );
}

/** Additions in progress: the method, where they stand, and what to do with them. */
function Additions({ additions }: { additions: Addition[] }) {
  const t = useT();
  const now = useNow();
  const queryClient = useQueryClient();
  const notify = useNotify();
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelAddition(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.satellites });
      notify(t("sat-addition-cancelled"));
    },
    onError: (error) => notify(messageOf(error)),
  });
  return (
    <Section title={t("sat-additions")} count={additions.length}>
      <RowList>
        {additions.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-3 px-5 py-4">
            <div className="min-w-0 flex-1 basis-56">
              <p className="font-medium text-ink">
                {a.name ?? a.method.label}
                <span className="font-normal text-ink-muted"> · {t(`sat-stage-${a.stage.replace("_", "-")}`)}</span>
              </p>
              <p className="text-[0.88rem] text-ink-muted">
                {a.name ? `${a.method.label} · ` : ""}
                {a.room ? `${t("sat-room", { room: a.room })} · ` : ""}
                <span className="tabular">{t("sat-expires-in", { remaining: remaining(a.expires_at, now) })}</span>
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <AddSatelliteButton resume={a} />
              <Button variant="ghost" size="sm" onClick={() => cancel.mutate(a.id)} disabled={cancel.isPending}>
                {t("sat-addition-cancel")}
              </Button>
            </div>
          </li>
        ))}
      </RowList>
    </Section>
  );
}
