import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { type Addition, api, keys, messageOf, type PairingRequest, type Satellite, satellitesQuery } from "@/api";
import { Ago } from "@/components/ago";
import { useNotify } from "@/components/notices";
import { Section } from "@/components/page";
import { Empty, Failure, Loading } from "@/components/states";
import { Status } from "@/components/status";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import { BrandMark, brandOf } from "@/lib/brands";
import { remaining } from "@/lib/dates";
import { CAPABILITY_ICON } from "@/lib/icons";
import { useCan, useMe } from "@/lib/session";
import { AddSatelliteButton, IdentifyButton } from "./add-satellite";
import { ApproveForm } from "./approve-form";

export function SatellitesList({
  approving,
  onApprove,
}: {
  approving?: string;
  onApprove: (id: string | undefined) => void;
}) {
  const t = useT();
  const satellites = useQuery(satellitesQuery);
  if (satellites.isPending) return <Loading lines={3} />;
  if (satellites.isError) return <Failure error={satellites.error} retry={() => void satellites.refetch()} />;
  const { pending, paired, additions } = satellites.data;
  const request = pending.find((p) => p.id === approving);
  return (
    <>
      {additions.length ? <Additions additions={additions} /> : null}
      {pending.length ? <Pending requests={pending} onApprove={onApprove} /> : null}
      <Section title={t("sat-paired")} count={paired.length}>
        {paired.length === 0 ? (
          <Empty hint={t("sat-paired-empty-hint")}>{t("sat-paired-empty")}</Empty>
        ) : (
          <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
            {paired.map((s) => (
              <PairedRow key={s.id} satellite={s} />
            ))}
          </ul>
        )}
      </Section>
      <ApproveDialog request={request} onClose={() => onApprove(undefined)} />
    </>
  );
}

function Pending({ requests, onApprove }: { requests: PairingRequest[]; onApprove: (id: string) => void }) {
  const t = useT();
  const canPair = useCan("satellites:write");
  const now = useNow();
  return (
    <Section title={t("sat-pending")} count={requests.length}>
      <ul className="grid gap-3 sm:grid-cols-2">
        {requests.map((r) => {
          const brand = brandOf(r.device.brand);
          return (
            <li key={r.id} className="rounded-md border border-rule bg-paper-raised p-5">
              <div>
                <div className="flex items-center gap-2">
                  {brand ? <BrandMark brand={brand} className="size-4 text-ink" /> : null}
                  <h3 className="font-mono text-[0.95rem] font-medium">{r.device.id}</h3>
                </div>
                <p className="mt-1 text-sm text-ink-muted">
                  {t("sat-model-room", { model: r.device.model, room: r.device.room })}
                </p>
                <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <Status tone="pending">
                    <span className="tabular">{t("sat-expires-in", { remaining: remaining(r.expires_at, now) })}</span>
                  </Status>
                  <span className="flex gap-1.5 text-ink-muted">
                    {r.capabilities.map((c) => {
                      const Icon = CAPABILITY_ICON[c.name];
                      return Icon ? <Icon key={c.name} className="size-3.5" aria-label={c.label} /> : null;
                    })}
                  </span>
                </p>
                <p className="mt-2 text-[0.88rem] text-ink-muted">
                  {r.methods.find((m) => m.id === r.recommended_method)?.hint}
                </p>
                {canPair ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => onApprove(r.id)}>
                      {t("sat-approve")}
                    </Button>
                    {r.can_identify ? <IdentifyButton pairing={r.id} /> : null}
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-ink-muted">{t("sat-approve-forbidden")}</p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function ApproveDialog({ request, onClose }: { request: PairingRequest | undefined; onClose: () => void }) {
  const t = useT();
  const me = useMe();
  return (
    <Dialog open={Boolean(request)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl font-normal">
            {t("sat-approve-title", { id: request?.device.id ?? "" })}
          </DialogTitle>
          <DialogDescription>
            {t("sat-approve-description", { assistant: me.assistant, room: request?.device.room ?? "" })}
          </DialogDescription>
        </DialogHeader>
        {request ? <ApproveForm request={request} onDone={onClose} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function PairedRow({ satellite: s }: { satellite: Satellite }) {
  const t = useT();
  const brand = brandOf(s.brand);
  return (
    <li>
      <Link
        to="/satellites/$satelliteId"
        params={{ satelliteId: s.id }}
        className="group grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-4 px-5 py-3.5 hover:bg-paper-sunken/60 sm:grid-cols-[1.5rem_minmax(0,1.4fr)_minmax(0,1fr)_12rem_1rem]"
      >
        {brand ? <BrandMark brand={brand} className="size-5 text-ink" /> : <span />}
        <span className="min-w-0">
          <span className="block text-ink">{s.name ?? <span className="font-mono text-sm">{s.id}</span>}</span>
          <span className="block text-[0.85rem] text-ink-muted">
            {s.name ? `${s.id} · ` : ""}
            {s.model} · {s.room}
          </span>
        </span>
        <span className="hidden gap-1.5 text-ink-muted sm:flex">
          {s.capabilities.map((c) => {
            const Icon = CAPABILITY_ICON[c.name];
            return Icon ? <Icon key={c.name} className="size-3.5" aria-label={c.label} /> : null;
          })}
        </span>
        <span>
          {s.connected === null ? (
            <Status tone="idle">{t("sat-state-unknown")}</Status>
          ) : s.connected ? (
            <Status tone="ok">{t("sat-state-connected")}</Status>
          ) : (
            <Status tone="attention">
              {t("sat-state-offline")}
              {s.last_seen_at ? (
                <>
                  {" "}
                  · <Ago iso={s.last_seen_at} />
                </>
              ) : null}
            </Status>
          )}
        </span>
        <ArrowRight className="hidden size-3.5 text-ink-faint group-hover:text-ink sm:block" aria-hidden="true" />
      </Link>
    </li>
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
      <ul className="divide-y divide-rule rounded-md border border-rule bg-paper-raised">
        {additions.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5">
            <div className="min-w-0 flex-1">
              <p className="text-ink">
                {a.name ?? a.method.label}
                <span className="text-ink-muted"> · {t(`sat-stage-${a.stage.replace("_", "-")}`)}</span>
              </p>
              <p className="text-[0.85rem] text-ink-muted">
                {a.name ? `${a.method.label} · ` : ""}
                {a.room ? `${t("sat-room", { room: a.room })} · ` : ""}
                <span className="tabular">{t("sat-expires-in", { remaining: remaining(a.expires_at, now) })}</span>
              </p>
            </div>
            <AddSatelliteButton resume={a} />
            <Button variant="ghost" size="sm" onClick={() => cancel.mutate(a.id)} disabled={cancel.isPending}>
              {t("sat-addition-cancel")}
            </Button>
          </li>
        ))}
      </ul>
    </Section>
  );
}
