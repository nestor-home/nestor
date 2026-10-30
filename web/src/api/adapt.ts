/** From the API's DTOs (generated) to what screens read (types.ts). The only place both meet. */
import type {
  AccountDto,
  ComponentDto,
  ConnectionDetailDto,
  ConnectionDto,
  ConnectorDto,
  FacetsDto,
  InvitationDto,
  InvitationPreviewDto,
  JournalEntryDto,
  JournalItemDto,
  MeDto,
  MemoryDto,
  PendingDto,
  PersonDto,
  PersonRefDto,
  SatelliteDto,
  ScopeDto,
  SystemDto,
  TaskDto,
  WatchDto,
} from "./dto";
import type {
  Account,
  Component,
  Connection,
  ConnectionDetail,
  Connector,
  Health,
  Invitation,
  InvitationPreview,
  JournalEvent,
  JournalFacets,
  JournalItem,
  Me,
  Memory,
  PairingRequest,
  Person,
  Satellite,
  Scope,
  SystemInfo,
  Task,
  Watch,
} from "./types";

const ref = (r: PersonRefDto | null | undefined) => r?.id ?? null;

/** The server's scopes as the screens group them: reading or changing a part of the admin. */
const SCOPES: Record<ScopeDto, Scope[]> = {
  "accounts.manage": ["accounts:read", "accounts:write"],
  "accounts.owners.manage": ["accounts:read", "accounts:write"],
  "household.read": ["people:read", "connections:read", "tasks:read", "watches:read", "memories:read"],
  "household.connections.manage": ["connections:read", "connections:write"],
  "own.connections.manage": ["connections:read", "connections:write"],
  "satellites.manage": ["satellites:read", "satellites:write"],
  "system.read": ["system:read", "satellites:read"],
  "journal.read.all": ["journal:read"],
  "journal.read.own": ["journal:read"],
  "memory.manage.all": ["memories:read", "memories:write"],
  "memory.manage.own": ["memories:read", "memories:write"],
  "tasks.manage": ["tasks:read", "tasks:write"],
  "tasks.manage.own": ["tasks:read", "tasks:write"],
  "watches.manage.all": ["watches:read", "watches:write"],
  "watches.manage.own": ["watches:read", "watches:write"],
};

export function scopes(dto: ScopeDto[]): Scope[] {
  return [...new Set(dto.flatMap((s) => SCOPES[s] ?? []))];
}

export function account(dto: AccountDto): Account {
  return {
    id: dto.id,
    login: dto.login,
    role: dto.role,
    role_label: dto.role_label,
    person: ref(dto.person),
    person_name: dto.person?.name ?? null,
    locale: dto.locale,
    disabled: dto.disabled,
    created_at: dto.created_at,
  };
}

export function me(dto: MeDto): Me {
  return {
    locale: dto.locale,
    account: account(dto.account),
    scopes: scopes(dto.scopes),
    csrf_token: dto.csrf_token,
    assistant: dto.agent?.name ?? dto.assistant,
    agent: dto.agent,
  };
}

export function invitation(dto: InvitationDto): Invitation {
  return {
    id: dto.id,
    role: dto.role,
    role_label: dto.role_label,
    person: ref(dto.person),
    person_name: dto.person?.name ?? null,
    status: dto.status,
    status_label: dto.status_label,
    created_at: dto.created_at,
    expires_at: dto.expires_at,
  };
}

export function preview(dto: InvitationPreviewDto): InvitationPreview {
  return {
    role: dto.role,
    role_label: dto.role_label,
    person_name: dto.person?.name ?? null,
    expires_at: dto.expires_at,
  };
}

export function person(dto: PersonDto): Person {
  return {
    id: dto.id,
    name: dto.name,
    channels: dto.channel_accounts,
    reach: dto.reach,
    presence: dto.presence ? { home: dto.presence.home, room: dto.presence.room, since: null } : null,
    account: dto.account?.id ?? null,
    account_login: dto.account?.login ?? null,
  };
}

export function journalItem(dto: JournalItemDto): JournalItem {
  const links = Object.fromEntries(Object.entries(dto.links).filter(([, v]) => v !== null && v !== undefined));
  return {
    id: String(dto.position),
    uid: dto.id,
    at: dto.at,
    type: dto.type,
    kind: dto.kind,
    kind_label: dto.kind_label,
    message: { id: dto.message.id, args: dto.message.args as Record<string, string | number> },
    text: dto.text,
    detail: dto.detail_text || dto.detail,
    reason: dto.reason
      ? {
          message: { id: dto.reason.message.id, args: dto.reason.message.args as Record<string, string | number> },
          text: dto.reason.text,
        }
      : null,
    people: dto.people.map((p) => p.id),
    channels: dto.channels,
    room: dto.room,
    tone: dto.tone,
    links,
    cause: dto.cause === null || dto.cause === undefined ? null : String(dto.cause),
    outcome: dto.outcome ? { ok: dto.outcome.ok, duration_s: dto.outcome.duration_s } : null,
    tool: dto.tool,
    brand: dto.brand,
  };
}

export function journalEvent(dto: JournalEntryDto): JournalEvent {
  return { ...journalItem(dto.item), record: dto.record as Record<string, unknown> };
}

export function facets(dto: FacetsDto): JournalFacets {
  return { ...dto };
}

export function connector(dto: ConnectorDto): Connector {
  return {
    kind: dto.kind,
    brand: dto.brand,
    title: dto.title,
    description: dto.description,
    auth: dto.auth,
    auth_label: dto.auth_label,
    inbound: dto.inbound,
    setup: dto.setup,
    fields: dto.fields.map((f) => ({
      name: f.name,
      label: f.label,
      secret: f.secret,
      optional: f.default !== null,
      placeholder: f.default,
    })),
    client: dto.oauth?.registered && dto.oauth.client_id ? { client_id: dto.oauth.client_id } : null,
    redirect_uri: dto.oauth?.redirect_uri ?? null,
    relayed: dto.oauth?.relayed ?? false,
  };
}

export function connection(dto: ConnectionDto): Connection {
  return {
    id: dto.id,
    kind: dto.kind,
    title: dto.title,
    account: dto.account,
    owner: ref(dto.owner),
    status: dto.status,
    status_label: dto.status_label,
    status_reason: null,
    confirm_writes: dto.confirm_writes,
    disabled_tools: dto.disabled_tools,
    created_at: dto.created_at,
    brand: dto.brand,
    last_used_at: dto.last_used_at,
    calls_today: dto.calls_today,
    watches: dto.watches,
  };
}

export function connectionDetail(dto: ConnectionDetailDto): ConnectionDetail {
  return { ...connection(dto), tools: dto.tools.map((t) => ({ ...t })) };
}

export function pending(dto: PendingDto, now = Date.now()): PairingRequest {
  return {
    id: dto.pairing_id,
    device: { ...dto.device, sdk: dto.sdk },
    capabilities: dto.capabilities,
    expires_at: new Date(now + dto.expires_in_s * 1000).toISOString(),
  };
}

export function satellite(dto: SatelliteDto): Satellite {
  return {
    id: dto.id,
    model: dto.model,
    room: dto.room,
    capabilities: dto.capabilities,
    paired_at: dto.paired_at,
    approved_by: ref(dto.approved_by),
    approved_by_name: dto.approved_by?.name ?? null,
    connected: dto.connected,
    last_seen_at: dto.last_seen_at,
    brand: dto.brand,
    sdk: dto.sdk,
    sdk_version: dto.sdk_version,
  };
}

export function task(dto: TaskDto): Task {
  return {
    id: dto.id,
    objective: dto.objective,
    executor: dto.executor,
    status: dto.status,
    status_label: dto.status_label,
    requested_by: ref(dto.requested_by),
    started_at: dto.started_at,
    ended_at: null,
    steps: dto.steps,
    result: dto.result,
    error: dto.error,
    origin: dto.origin,
    delivered: dto.delivered,
  };
}

export function watch(dto: WatchDto): Watch {
  return {
    id: dto.id,
    what: dto.what,
    owner: ref(dto.owner),
    kinds: dto.kinds,
    keywords: dto.keywords,
    once: dto.once,
    created_at: dto.created_at,
    until: dto.until,
    origin: dto.origin,
    triggered: dto.triggered,
    last_triggered_at: dto.last_triggered_at,
  };
}

export function memory(dto: MemoryDto): Memory {
  return {
    id: dto.id,
    text: dto.text,
    about: ref(dto.about),
    told_by: ref(dto.told_by),
    channel: dto.learnt_in,
    updated_at: dto.updated_at,
    learnt_event: dto.learnt_event === null ? null : String(dto.learnt_event),
    session: dto.session,
    editable: dto.editable,
  };
}

const HEALTH: Record<string, Health> = { started: "ok", degraded: "degraded", unavailable: "down" };

export function component(dto: ComponentDto, index: number): Component {
  return {
    id: `${dto.slot}-${index}`,
    slot: dto.slot,
    name: dto.name,
    adapter: dto.adapter,
    brand: dto.brand,
    version: dto.version,
    distribution: dto.distribution,
    health: dto.health ? (HEALTH[dto.health] ?? "unknown") : "unknown",
    health_detail: dto.health_detail,
    capabilities: dto.capabilities,
    details: dto.details,
  };
}

export function system(dto: SystemDto): SystemInfo {
  return { nestor: dto.nestor, agent: dto.agent, components: dto.components.map(component) };
}
