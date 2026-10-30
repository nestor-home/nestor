/**
 * Adding a satellite from the admin. The person picks how the proof travels:
 * - a device code: the device shows or says 6 digits once it asks; the person tells the waiting
 *   devices apart (identify) and types the code of the right one;
 * - an enrollment code: made here, given to the device (typed, QR, configuration); the device
 *   presenting it is paired at once.
 * Progress is the addition's `stage`, polled while the sheet is open.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight, ChevronRight, Plus } from "lucide-react";
import { type FormEvent, useState } from "react";
import {
  type Addition,
  additionQuery,
  api,
  keys,
  messageOf,
  type PairingMethod,
  type PairingMethodId,
  type PairingRequest,
  pairingMethodsQuery,
  type StartedAddition,
  satellitesQuery,
} from "@/api";
import { AgentFigure } from "@/components/agent-figure";
import { CopyField } from "@/components/copy-field";
import { Field } from "@/components/field";
import { useNotify } from "@/components/notices";
import { FormSheet } from "@/components/overlay-form";
import { QrCode } from "@/components/qr-code";
import { Failure, FormError, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useNow } from "@/hooks/use-now";
import { useT } from "@/i18n";
import { remaining } from "@/lib/dates";
import { cn } from "@/lib/utils";
import { ApproveForm } from "./approve-form";

/** What a satellite may be allowed to do, when the person narrows it before the device is known. */
export const KNOWN_CAPABILITIES = [
  "audio.capture",
  "audio.playback",
  "audio.speech_activity",
  "vision.person_detection",
  "expression.emotion",
  "motion.head",
  "device.identify",
] as const;

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** Rooms are slugs on the wire: "Chambre de Jules" becomes "chambre-de-jules". */
export function roomSlug(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function AddSatelliteButton({ resume }: { resume?: Addition }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <FormSheet
      open={open}
      onOpenChange={setOpen}
      title={t("sat-add-title")}
      trigger={
        resume ? (
          <Button variant="outline" size="sm">
            {t("sat-addition-follow")}
          </Button>
        ) : (
          <Button>
            <Plus /> {t("sat-add")}
          </Button>
        )
      }
    >
      {(close) => <AddSatellite resume={resume} close={close} />}
    </FormSheet>
  );
}

function AddSatellite({ resume, close }: { resume?: Addition; close: () => void }) {
  const [started, setStarted] = useState<StartedAddition | null>(
    resume ? { addition: resume, code: null, uri: null } : null,
  );
  if (!started) return <Choose onStarted={setStarted} />;
  return <Follow started={started} close={close} restart={() => setStarted(null)} />;
}

// -- 1. how, and what for ---------------------------------------------------------------------------

function Choose({ onStarted }: { onStarted: (started: StartedAddition) => void }) {
  const t = useT();
  const methods = useQuery(pairingMethodsQuery);
  const [chosen, setChosen] = useState<PairingMethodId | null>(null);
  const [name, setName] = useState("");
  const [room, setRoom] = useState("");
  const [limited, setLimited] = useState<Set<string> | null>(null);
  const [roomError, setRoomError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const method = chosen ?? methods.data?.recommended ?? null;
  const start = useMutation({
    mutationFn: () =>
      api.startAddition({
        method: method as PairingMethodId,
        name: name.trim() || undefined,
        room: room.trim() ? roomSlug(room) : undefined,
        capabilities: limited ? [...limited].sort() : undefined,
      }),
    onSuccess: (started) => {
      void queryClient.invalidateQueries({ queryKey: keys.satellites });
      onStarted(started);
    },
  });
  if (methods.isPending) return <Loading lines={3} />;
  if (methods.isError) return <Failure error={methods.error} retry={() => void methods.refetch()} />;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (room.trim() && !SLUG.test(roomSlug(room))) {
      setRoomError(t("sat-add-room-invalid"));
      return;
    }
    setRoomError(null);
    start.mutate();
  };
  const groups: { proof: PairingMethod["proof"]; title: string }[] = [
    { proof: "device_code", title: t("sat-add-device-code") },
    { proof: "enrollment_code", title: t("sat-add-enrollment-code") },
  ];
  return (
    <form onSubmit={submit} className="grid gap-7 pt-5" noValidate>
      <fieldset className="grid gap-5">
        <legend className="mb-3 text-[0.95rem] font-medium text-ink">{t("sat-add-how")}</legend>
        {groups.map((group) => (
          <div key={group.proof}>
            <p className="mb-2 text-[0.88rem] text-ink-muted">{group.title}</p>
            <ToggleGroup
              aria-label={group.title}
              value={method ? [method] : []}
              onValueChange={(value: string[]) => {
                const next = value.find((v) => v !== method);
                if (next) setChosen(next as PairingMethodId);
              }}
              className="grid w-full gap-2"
            >
              {methods.data.methods
                .filter((m) => m.proof === group.proof)
                .map((m) => (
                  <ToggleGroupItem
                    key={m.id}
                    value={m.id}
                    className="h-auto w-full justify-start rounded-md border border-rule bg-paper-raised px-3.5 py-3 text-left whitespace-normal data-[pressed]:border-ink data-[pressed]:bg-paper-sunken"
                  >
                    <span className="grid gap-0.5">
                      <span className="flex flex-wrap items-baseline gap-2 text-[0.98rem] text-ink">
                        {m.label}
                        {m.id === methods.data.recommended ? (
                          <span className="rounded-full bg-ember-soft px-2 py-px text-[0.75rem] text-ember">
                            {t("sat-add-recommended")}
                          </span>
                        ) : null}
                      </span>
                      <span className="text-[0.88rem] font-normal text-ink-muted">{m.hint}</span>
                    </span>
                  </ToggleGroupItem>
                ))}
            </ToggleGroup>
          </div>
        ))}
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("sat-add-name")} htmlFor="sat-add-name" hint={t("sat-add-optional")}>
          <Input id="sat-add-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={64} />
        </Field>
        <Field
          label={t("sat-add-room")}
          htmlFor="sat-add-room"
          hint={room.trim() ? t("sat-add-room-as", { room: roomSlug(room) }) : t("sat-add-room-hint")}
          error={roomError}
        >
          <Input id="sat-add-room" value={room} onChange={(e) => setRoom(e.target.value)} />
        </Field>
      </div>

      <Collapsible open={limited !== null} onOpenChange={(on) => setLimited(on ? new Set(KNOWN_CAPABILITIES) : null)}>
        <CollapsibleTrigger className="group/caps inline-flex items-center gap-1.5 text-[0.92rem] text-ink-muted hover:text-ink">
          <ChevronRight
            className="size-3.5 transition-transform group-data-panel-open/caps:rotate-90"
            aria-hidden="true"
          />
          {t("sat-add-limit")}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {KNOWN_CAPABILITIES.map((name) => (
              <li key={name}>
                <label htmlFor={`cap-${name}`} className="flex items-start gap-2.5 text-[0.92rem]">
                  <Checkbox
                    id={`cap-${name}`}
                    checked={limited?.has(name) ?? true}
                    onCheckedChange={(on) =>
                      setLimited((current) => {
                        const next = new Set(current ?? KNOWN_CAPABILITIES);
                        if (on) next.add(name);
                        else next.delete(name);
                        return next;
                      })
                    }
                    className="mt-0.5"
                  />
                  <span>
                    {t(`sat-cap-${name.replace(/[._]/g, "-")}`)}
                    <code className="block text-[0.72rem] text-ink-faint">{name}</code>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </CollapsibleContent>
      </Collapsible>

      <FormError error={start.error} />
      <div className="flex justify-end">
        <Button type="submit" variant="accent" disabled={!method || start.isPending}>
          {start.isPending ? "…" : t("sat-add-start")}
        </Button>
      </div>
    </form>
  );
}

// -- 2. following it until the device is paired -----------------------------------------------------

function Follow({ started, close, restart }: { started: StartedAddition; close: () => void; restart: () => void }) {
  const t = useT();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const live = useQuery({ ...additionQuery(started.addition.id), initialData: started.addition });
  const addition = live.data;
  const cancel = useMutation({
    mutationFn: () => api.cancelAddition(addition.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.satellites });
      notify(t("sat-addition-cancelled"));
      close();
    },
  });
  const active = addition.stage === "waiting" || addition.stage === "device_seen";
  return (
    <div className="grid gap-6 pt-5">
      <Progress addition={addition} />
      {addition.stage === "paired" ? (
        <Paired addition={addition} close={close} />
      ) : addition.stage === "cancelled" || addition.stage === "expired" ? (
        <div className="grid gap-3">
          <p className="text-ink">{t(addition.stage === "expired" ? "sat-addition-expired" : "sat-addition-over")}</p>
          <Button variant="outline" className="justify-self-start" onClick={restart}>
            {t("sat-addition-again")}
          </Button>
        </div>
      ) : addition.method.proof === "enrollment_code" ? (
        <Enrollment started={started} addition={addition} />
      ) : (
        <Candidates addition={addition} />
      )}
      {active ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-4">
          <Countdown until={addition.expires_at} />
          <Button variant="ghost" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
            {t("sat-addition-cancel")}
          </Button>
        </div>
      ) : null}
      <FormError error={cancel.error} />
    </div>
  );
}

const STEPS = ["waiting", "device_seen", "paired"] as const;

/** Waiting, then device seen (device codes), then paired: where the addition stands. */
function Progress({ addition }: { addition: Addition }) {
  const t = useT();
  const steps: readonly string[] = addition.method.proof === "device_code" ? STEPS : ["waiting", "paired"];
  const at = steps.indexOf(addition.stage);
  return (
    <ol aria-label={t("sat-addition-progress")} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.9rem]">
      {steps.map((step, i) => (
        <li
          key={step}
          aria-current={i === at ? "step" : undefined}
          className={cn("inline-flex items-center gap-1.5", i <= at ? "text-ink" : "text-ink-faint")}
        >
          {i > 0 ? <span aria-hidden="true" className="h-px w-5 bg-rule-strong" /> : null}
          <span
            aria-hidden="true"
            className={cn(
              "size-2 rounded-full",
              i < at || addition.stage === "paired" ? "bg-sage" : i === at ? "mind-breathe bg-ember" : "bg-rule-strong",
            )}
          />
          {t(`sat-stage-${step.replace("_", "-")}`)}
        </li>
      ))}
    </ol>
  );
}

function Countdown({ until }: { until: string }) {
  const t = useT();
  const now = useNow();
  return (
    <p className="text-[0.88rem] text-ink-muted tabular">{t("sat-expires-in", { remaining: remaining(until, now) })}</p>
  );
}

/** The enrollment code, once: grouped, as a QR code, and ready to paste where the device reads it. */
function Enrollment({ started, addition }: { started: StartedAddition; addition: Addition }) {
  const t = useT();
  const { code, uri } = started;
  if (!code) return <p className="text-ink-muted">{t("sat-addition-code-once")}</p>;
  const canonical = code.replace(/-/g, "");
  return (
    <div className="grid gap-6">
      <p className="text-ink">{addition.method.hint}</p>
      <div className="grid items-start gap-6 sm:grid-cols-[auto_minmax(0,1fr)]">
        {uri ? (
          <QrCode
            value={uri}
            label={t("sat-addition-qr", { code })}
            className="size-44 justify-self-center sm:size-48"
          />
        ) : null}
        <div className="grid content-start gap-4">
          <div>
            <p className="text-[0.88rem] text-ink-muted">{t("sat-addition-code")}</p>
            <p className="font-mono text-[2.2rem] leading-tight tracking-[0.12em] text-ink">{code}</p>
          </div>
          <CopyField value={code} label={t("sat-addition-code")} />
          {uri ? (
            <CopyField value={uri} label={t("sat-addition-uri")} />
          ) : (
            <p className="text-[0.92rem] text-ink-muted">{t("sat-addition-no-uri")}</p>
          )}
        </div>
      </div>
      <div className="grid gap-2">
        <p className="text-[0.92rem] font-medium text-ink">{t("sat-addition-examples")}</p>
        <Example
          label={t("sat-example-env")}
          value={uri ? `NESTOR_PAIRING_URI="${uri}"` : `NESTOR_PAIRING_CODE=${canonical}`}
        />
        <Example
          label={t("sat-example-cli")}
          value={
            uri ? `nestor-satellite run --pairing-uri "${uri}"` : `nestor-satellite run --pairing-code ${canonical}`
          }
        />
        <Example
          label={t("sat-example-service")}
          value={`Environment=NESTOR_PAIRING_${uri ? `URI=${uri}` : `CODE=${canonical}`}`}
        />
      </div>
      <p className="flex items-center gap-2 text-ink-muted">
        <AgentFigure state="listening" size="sm" />
        {t("sat-addition-waiting-enrollment")}
      </p>
    </div>
  );
}

function Example({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1">
      <span className="text-[0.82rem] text-ink-muted">{label}</span>
      <CopyField value={value} label={label} />
    </div>
  );
}

/** The devices waiting that may be this one: tell them apart, then type the code of the right one. */
function Candidates({ addition }: { addition: Addition }) {
  const t = useT();
  const satellites = useQuery({ ...satellitesQuery, refetchInterval: 1_500 });
  const [chosen, setChosen] = useState<string | null>(null);
  const waiting = (satellites.data?.pending ?? []).filter((p) => addition.candidates.includes(p.id));
  if (addition.stage === "waiting" || !waiting.length)
    return (
      <div className="grid gap-2">
        <p className="flex items-center gap-2 text-ink">
          <AgentFigure state="listening" size="sm" />
          {t("sat-addition-waiting-device")}
        </p>
        <p className="text-[0.92rem] text-ink-muted">{addition.method.hint}</p>
      </div>
    );
  const request = waiting.find((p) => p.id === chosen) ?? (waiting.length === 1 ? waiting[0] : undefined);
  return (
    <div className="grid gap-5">
      <ul className="grid gap-2">
        {waiting.map((p) => (
          <Candidate key={p.id} request={p} chosen={request?.id === p.id} onChoose={() => setChosen(p.id)} />
        ))}
      </ul>
      {request ? (
        <ApproveForm
          key={request.id}
          request={request}
          additionId={addition.id}
          granted={addition.capabilities?.map((c) => c.name)}
        />
      ) : null}
    </div>
  );
}

function Candidate({ request, chosen, onChoose }: { request: PairingRequest; chosen: boolean; onChoose: () => void }) {
  const t = useT();
  return (
    <li
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border px-4 py-3",
        chosen ? "border-ink bg-paper-sunken" : "border-rule bg-paper-raised",
      )}
    >
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[0.95rem] text-ink">{request.device.id}</p>
        <p className="text-[0.88rem] text-ink-muted">
          {t("sat-model-room", { model: request.device.model, room: request.device.room })}
        </p>
      </div>
      {request.can_identify ? <IdentifyButton pairing={request.id} /> : null}
      {chosen ? null : (
        <Button variant="outline" size="sm" onClick={onChoose}>
          {t("sat-addition-this-one")}
        </Button>
      )}
    </li>
  );
}

/** Asks a device to make itself noticed (light, motion or sound). */
export function IdentifyButton({ pairing, device }: { pairing?: string; device?: string }) {
  const t = useT();
  const notify = useNotify();
  const identify = useMutation({
    mutationFn: () => (pairing ? api.identifyPending(pairing) : api.identify(device ?? "")),
    onSuccess: () => notify(t("sat-identify-sent")),
    onError: (error) => notify(messageOf(error)),
  });
  return (
    <Button variant="ghost" size="sm" onClick={() => identify.mutate()} disabled={identify.isPending}>
      {t("sat-identify")}
    </Button>
  );
}

function Paired({ addition, close }: { addition: Addition; close: () => void }) {
  const t = useT();
  return (
    <div className="flex flex-wrap items-center gap-4">
      <AgentFigure state="laughing" size="md" />
      <div className="grid gap-1">
        <p className="text-[1.05rem] text-ink">
          {t("sat-addition-paired", { name: addition.name ?? addition.device_id ?? "" })}
        </p>
        {addition.device_id ? (
          <Link
            to="/satellites/$satelliteId"
            params={{ satelliteId: addition.device_id }}
            onClick={close}
            className="inline-flex items-center gap-1 text-[0.92rem] text-ember hover:underline"
          >
            {t("sat-addition-see")} <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        ) : null}
      </div>
    </div>
  );
}
