import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { type PairingRequest, type Satellite, satellitesQuery } from "@/api";
import { Ago } from "@/components/ago";
import { Dither } from "@/components/dither";
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
  const { pending, paired } = satellites.data;
  const request = pending.find((p) => p.id === approving);
  return (
    <>
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
            <li
              key={r.id}
              className="corner-marks relative overflow-hidden rounded-md border border-rule bg-paper-raised p-5"
            >
              <Dither shape="ramp-left" from={0.35} to={0} className="absolute inset-y-0 right-0 w-1/3 text-amber/50" />
              <div className="relative">
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
                {canPair ? (
                  <Button size="sm" className="mt-4" onClick={() => onApprove(r.id)}>
                    {t("sat-approve")}
                  </Button>
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
          <span className="block truncate font-mono text-sm text-ink">{s.id}</span>
          <span className="block text-xs text-ink-muted">
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
