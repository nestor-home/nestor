/**
 * The mock state as the API sends it: every answer is built as the generated DTO type, so a change
 * in `web/openapi.json` that the mocks do not follow fails the typecheck here.
 */
import type {
  Account,
  Component,
  Connection,
  ConnectionDetail,
  Connector,
  Invitation,
  JournalItem,
  Memory,
  PairingRequest,
  Person,
  Satellite,
  Task,
  Watch,
} from "@/api";
import type {
  AccountDto,
  ComponentDto,
  ConnectionDetailDto,
  ConnectionDto,
  ConnectorDto,
  InvitationDto,
  JournalItemDto,
  MeDto,
  MemoryDto,
  PendingDto,
  PersonDto,
  PersonRefDto,
  SatelliteDto,
  TaskDto,
  WatchDto,
} from "@/api/dto";
import { db } from "./db";
import { ASSISTANT, SCOPES } from "./fixtures";

export function personRef(id: string | null | undefined): PersonRefDto | null {
  if (!id) return null;
  return { id, name: db.people.find((p) => p.id === id)?.name ?? id };
}

export function accountDto(a: Account): AccountDto {
  return {
    id: a.id,
    login: a.login,
    role: a.role,
    role_label: a.role_label,
    person: a.person ? { id: a.person, name: a.person_name ?? a.person } : null,
    disabled: a.disabled,
    created_at: a.created_at,
    locale: a.locale,
  };
}

export function meDto(a: Account, lang: string): MeDto {
  return {
    account: accountDto(a),
    locale: a.locale ?? lang,
    scopes: SCOPES[a.role],
    csrf_token: "mock-csrf-token",
    assistant: ASSISTANT,
    agent: { name: ASSISTANT, status: "online" },
  };
}

export function invitationDto(i: Invitation): InvitationDto {
  return {
    id: i.id,
    role: i.role,
    role_label: i.role_label,
    person: personRef(i.person),
    status: i.status,
    status_label: i.status_label,
    created_at: i.created_at,
    expires_at: i.expires_at,
  };
}

export function personDto(p: Person): PersonDto {
  const account = db.accounts.find((a) => a.id === p.account);
  return {
    id: p.id,
    name: p.name,
    channel_accounts: p.channels,
    reach: p.reach,
    presence: p.presence ? { home: p.presence.home, room: p.presence.room } : null,
    connections: db.connections.filter((c) => c.owner === p.id).map(connectionDto),
    account: account ? accountDto(account) : null,
  };
}

export function connectorDto(c: Connector): ConnectorDto {
  return {
    kind: c.kind,
    brand: c.brand,
    title: c.title,
    description: c.description,
    auth: c.auth,
    auth_label: c.auth_label,
    setup: c.setup,
    fields: c.fields.map((f) => ({
      name: f.name,
      label: f.label,
      secret: f.secret,
      default: f.optional ? (f.placeholder ?? "") : null,
    })),
    inbound: c.inbound,
    oauth:
      c.auth === "oauth2"
        ? {
            registered: c.client !== null,
            client_id: c.client?.client_id ?? null,
            redirect_uri: c.redirect_uri ?? "",
            relayed: c.relayed,
          }
        : null,
  };
}

export function connectionDto(c: Connection): ConnectionDto {
  const tools = db.tools[c.id] ?? [];
  return {
    id: c.id,
    kind: c.kind,
    brand: c.brand,
    title: c.title,
    account: c.account,
    owner: personRef(c.owner),
    status: c.status,
    status_label: c.status_label,
    confirm_writes: c.confirm_writes,
    disabled_tools: tools.filter((t) => !t.enabled).map((t) => t.name),
    created_at: c.created_at,
    last_used_at: c.last_used_at,
    calls_today: c.calls_today,
    watches: c.watches,
  };
}

export function connectionDetailDto(c: Connection | ConnectionDetail): ConnectionDetailDto {
  return {
    ...connectionDto(c),
    tools: (db.tools[c.id] ?? []).map((t) => ({
      name: t.name,
      description: t.description,
      risk: t.risk,
      risk_label: t.risk_label,
      enabled: t.enabled,
    })),
  };
}

export function pendingDto(p: PairingRequest): PendingDto {
  return {
    pairing_id: p.id,
    device: { id: p.device.id, model: p.device.model, room: p.device.room, brand: p.device.brand },
    capabilities: p.capabilities,
    sdk: p.device.sdk,
    sdk_version: null,
    expires_in_s: Math.max(0, Math.round((new Date(p.expires_at).getTime() - Date.now()) / 1000)),
  };
}

export function satelliteDto(s: Satellite): SatelliteDto {
  return {
    id: s.id,
    model: s.model,
    room: s.room,
    brand: s.brand,
    sdk: s.sdk,
    sdk_version: s.sdk_version,
    capabilities: s.capabilities,
    paired_at: s.paired_at,
    last_seen_at: s.last_seen_at,
    approved_by: personRef(s.approved_by),
    connected: s.connected,
  };
}

export function taskDto(t: Task): TaskDto {
  return {
    id: t.id,
    objective: t.objective,
    executor: t.executor,
    status: t.status,
    status_label: t.status_label,
    requested_by: personRef(t.requested_by),
    origin: { session: t.origin?.session ?? "", channel: t.origin?.channel ?? "" },
    delivered: t.delivered,
    started_at: t.started_at,
    steps: t.steps,
    result: t.result,
    error: t.error,
  };
}

export function watchDto(w: Watch): WatchDto {
  return {
    id: w.id,
    what: w.what,
    keywords: w.keywords,
    kinds: w.kinds,
    owner: personRef(w.owner),
    once: w.once,
    created_at: w.created_at,
    until: w.until,
    origin: w.origin ? { session: w.origin.session ?? "", channel: w.origin.channel ?? "" } : null,
    triggered: w.triggered,
    last_triggered_at: w.last_triggered_at,
  };
}

export function memoryDto(m: Memory): MemoryDto {
  return {
    id: m.id,
    text: m.text,
    about: personRef(m.about),
    told_by: personRef(m.told_by),
    learnt_in: m.channel,
    session: m.session,
    learnt_event: m.learnt_event === null ? null : Number(m.learnt_event),
    created_at: m.updated_at,
    updated_at: m.updated_at,
    editable: m.editable,
  };
}

const HEALTH = { ok: "started", degraded: "degraded", down: "unavailable", unknown: null } as const;

export function componentDto(c: Component): ComponentDto {
  return {
    slot: c.slot,
    name: c.name,
    adapter: c.adapter,
    brand: c.brand,
    version: c.version,
    distribution: c.distribution,
    capabilities: c.capabilities,
    health: HEALTH[c.health],
    health_detail: c.health_detail,
    details: c.details,
  };
}

const LINK_KEYS = [
  "session",
  "turn",
  "call",
  "task",
  "watch",
  "delivery",
  "connection",
  "satellite",
  "memory",
] as const;

/** A journal item of the mock (view shape, id = position) as the API sends it. */
export function journalItemDto(item: JournalItem, kindLabel: string): JournalItemDto {
  return {
    position: Number(item.id),
    id: item.uid,
    at: item.at,
    type: item.type,
    kind: item.kind as JournalItemDto["kind"],
    kind_label: kindLabel,
    message: item.message,
    text: item.text,
    detail: item.detail,
    detail_message: null,
    detail_text: "",
    reason: item.reason,
    tone: item.tone,
    people: item.people.map((id) => personRef(id) ?? { id, name: id }),
    channels: item.channels,
    room: item.room,
    tool: item.tool,
    outcome: item.outcome ? { ok: item.outcome.ok, duration_s: item.outcome.duration_s ?? 0 } : null,
    brand: item.brand,
    links: Object.fromEntries(LINK_KEYS.map((k) => [k, item.links[k] ?? null])) as JournalItemDto["links"],
    cause: item.cause === null ? null : Number(item.cause),
  };
}
