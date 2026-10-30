/**
 * The admin's view of the API v1: what screens read. `adapt.ts` builds these from the generated
 * DTOs (`dto.ts`, from `web/openapi.json`), so a change of the API breaks the build there, not on
 * a screen. Differences are deliberate and few: people as ids (names come from `/household/people`),
 * a journal item's `id` is its position (the cursor), scopes grouped as the screens use them.
 */

export type Id = string;
export type Instant = string; // ISO 8601 with offset

// -- who is using the admin -----------------------------------------------------------------------

export type Role = "owner" | "admin" | "member" | "guest";
export type Locale = "en" | "fr";

/** What a screen may show or do, derived from the server's finer scopes (adapt.ts). */
export type Scope =
  | "journal:read"
  | "connections:read"
  | "connections:write"
  | "satellites:read"
  | "satellites:write"
  | "system:read"
  | "tasks:read"
  | "tasks:write"
  | "watches:read"
  | "watches:write"
  | "memories:read"
  | "memories:write"
  | "people:read"
  | "accounts:read"
  | "accounts:write"
  | "config:manage"
  | "agent:read";

export interface Account {
  id: Id;
  login: string;
  role: Role;
  role_label: string;
  person: Id | null;
  person_name: string | null;
  locale: string | null; // null: the household's language
  disabled: boolean;
  created_at: Instant;
  last_seen_at: Instant | null;
}

/** A message the server owns: its catalogue id and arguments, and its text in the account's locale. */
export interface Message {
  id: string;
  args: Record<string, string | number>;
}

export interface Rendered {
  message: Message;
  text: string;
}

export interface Agent {
  name: string; // the instance's persona: "Richie", "Alfred"
  status: "online" | "degraded";
}

export interface Me {
  locale: string; // the language the server speaks to this account
  restart_required: boolean; // the configuration changed since Nestor started
  pending_changes: string[]; // which parts, as paths: "persona.name"
  account: Account;
  scopes: Scope[];
  csrf_token: string;
  assistant: string;
  agent: Agent;
}

export interface Credentials {
  login: string;
  password: string;
}

export type InvitationStatus = "pending" | "accepted" | "expired" | "revoked";

export interface Invitation {
  id: Id;
  role: Role;
  role_label: string;
  person: Id | null;
  person_name: string | null;
  status: InvitationStatus;
  status_label: string;
  created_at: Instant;
  expires_at: Instant;
}

export interface InvitationCreated {
  invitation: Invitation;
  link: string; // the one-time link to hand over; never shown again
}

export interface InvitationPreview {
  role: Role;
  role_label: string;
  person_name: string | null;
  expires_at: Instant;
}

export interface NewInvitation {
  role: Role;
  person: Id | null;
}

export interface AcceptInvitation {
  login: string;
  password: string;
}

export interface AccountChange {
  role?: Role;
  disabled?: boolean;
}

// -- the household --------------------------------------------------------------------------------

export interface Presence {
  home: boolean | null; // null: unknown
  room: string | null;
  since: Instant | null;
}

export interface Person {
  id: Id;
  name: string;
  channels: string[]; // where they are recognised: "voice", "telegram:@mathis"
  reach: string | null; // where unprompted messages go first
  presence: Presence | null; // null without a home system
  account: Id | null; // their admin account, if any
  account_login: string | null;
}

// -- journal --------------------------------------------------------------------------------------

export type Tone = "normal" | "decision" | "warning";

/**
 * Identifiers tying an event to the others of its story. The journal builds threads (a
 * conversation: turns and the tool calls they caused) and chains (a watch triggered → triaged →
 * announced → followed up; a task started → progressing → ended → delivered) from these only.
 */
export interface EventLinks {
  session?: Id;
  turn?: Id;
  call?: Id;
  task?: Id;
  watch?: Id;
  delivery?: Id;
  connection?: Id;
  satellite?: string;
  memory?: Id;
}

export interface JournalItem {
  id: Id; // the position in the journal, as a string: the cursor and the drawer's `event=`
  uid: Id; // the event's own id
  at: Instant;
  type: string; // "conversation.user_turn"
  kind: string; // "conversation", "delivery", "tool", "task", "watch"…
  kind_label: string;
  message: Message;
  text: string;
  detail: string; // what was said, the arguments, the outcome
  reason: Rendered | null;
  people: Id[];
  channels: string[];
  room: string | null;
  tone: Tone;
  links: EventLinks;
  cause: Id | null; // the position of the event that led to this one
  outcome: { ok: boolean; duration_s: number | null } | null;
  tool: string | null;
  brand: string | null;
}

export interface JournalEvent extends JournalItem {
  record: Record<string, unknown>;
}

export interface JournalPage {
  items: JournalItem[];
  next: Id | null;
}

export interface JournalFilters {
  kinds?: string[];
  person?: Id;
  channel?: string;
  room?: string;
  q?: string;
  from?: Instant;
  to?: Instant;
  tone?: Tone;
  session?: Id;
  task?: Id;
  watch?: Id;
  connection?: Id;
  satellite?: string;
}

export interface Facet {
  key: string;
  label: string;
  count: number;
}

export interface JournalFacets {
  total: number;
  truncated: boolean; // counted over the latest events only
  kinds: Facet[];
  people: Facet[];
  channels: Facet[];
  rooms: Facet[];
  histogram: { from: Instant; to: Instant; bucket_s: number; counts: number[] };
}

// -- connectors and connections -------------------------------------------------------------------

export type AuthKind = "oauth2" | "secret" | "none";
export type ConnectionStatus = "connected" | "needs_reauth" | "error";
export type Risk = "read" | "write" | "sensitive";

export interface ConnectorField {
  name: string;
  label: string;
  secret: boolean;
  optional: boolean; // it has a default
  placeholder: string | null; // its default, shown as an example
}

export interface Connector {
  kind: string;
  brand: string | null;
  title: string;
  description: string;
  auth: AuthKind;
  auth_label: string;
  inbound: string[];
  setup: string;
  fields: ConnectorField[];
  client: { client_id: string } | null; // the household's OAuth client, once registered
  redirect_uri: string | null;
  relayed: boolean;
}

export interface Connection {
  id: Id;
  kind: string;
  title: string;
  account: string;
  owner: Id | null;
  status: ConnectionStatus;
  status_label: string;
  status_reason: string | null; // why it needs a look, in the reader's language
  confirm_writes: boolean;
  disabled_tools: string[];
  created_at: Instant;
  brand: string | null;
  last_used_at: Instant | null;
  calls_today: number;
  watches: number;
}

export interface Tool {
  name: string;
  description: string;
  risk: Risk;
  risk_label: string;
  enabled: boolean;
}

export interface ConnectionDetail extends Connection {
  tools: Tool[];
}

export interface OAuthClient {
  client_id: string;
  client_secret: string;
}

export interface ConnectRequest {
  person: Id | null;
  replaces: Id | null;
  values: Record<string, string>;
}

export type ConnectResult = { kind: "redirect"; url: string } | { kind: "connected"; connection: Connection };

export interface ToolSettings {
  disabled_tools: string[];
  confirm_writes: boolean;
}

// -- satellites -----------------------------------------------------------------------------------

export interface Capability {
  name: string;
  label: string;
}

export interface PairingRequest {
  id: Id; // the pairing id
  device: { id: string; model: string; room: string; brand: string | null; sdk: string | null };
  capabilities: Capability[];
  expires_at: Instant; // computed from `expires_in_s` when received
}

export interface Satellite {
  id: string;
  model: string;
  room: string;
  capabilities: Capability[];
  paired_at: Instant;
  approved_by: Id | null;
  approved_by_name: string | null;
  connected: boolean | null;
  last_seen_at: Instant | null;
  brand: string | null;
  sdk: string | null;
  sdk_version: string | null;
}

export interface Satellites {
  pending: PairingRequest[];
  paired: Satellite[];
}

export interface Approval {
  code: string;
  capabilities: string[];
}

// -- tasks, watches, memories ---------------------------------------------------------------------

export type TaskStatus = "running" | "completed" | "failed" | "cancelled";

export interface Task {
  id: Id;
  objective: string;
  executor: string;
  status: TaskStatus;
  status_label: string;
  requested_by: Id | null;
  started_at: Instant;
  ended_at: Instant | null;
  steps: string[];
  result: string | null;
  error: string | null;
  origin: { session: Id | null; channel: string | null } | null;
  delivered: { at: Instant; channel: string; room: string | null } | null;
}

export interface Tasks {
  running: Task[];
  recent: Task[];
}

export interface Watch {
  id: Id;
  what: string;
  owner: Id | null;
  kinds: string[];
  keywords: string[];
  once: boolean;
  created_at: Instant;
  until: Instant | null;
  origin: { session: Id | null; channel: string | null } | null;
  triggered: number;
  last_triggered_at: Instant | null;
}

export interface Watches {
  watches: Watch[];
  sources: string[]; // inbound kinds available right now: ["mail"]
}

export interface Memory {
  id: Id;
  text: string;
  about: Id | null;
  told_by: Id | null;
  channel: string | null;
  updated_at: Instant;
  learnt_event: Id | null; // the journal position it was recorded at
  session: Id | null;
  editable: boolean;
}

export interface MemoryQuery {
  q?: string;
  about?: Id;
}

// -- system -------------------------------------------------------------------------------------

export type Slot = string; // "model", "speech", "executor", "channel", "presence", "tools", "connector", "satellite", "storage"…
export type Health = "ok" | "degraded" | "down" | "unknown";

export interface Component {
  id: Id;
  slot: Slot;
  name: string;
  adapter: string;
  brand: string | null;
  version: string | null;
  distribution: string | null;
  health: Health;
  health_detail: string | null;
  capabilities: string[];
  details: Record<string, string>;
}

export interface SystemInfo {
  nestor: { version: string };
  agent: Agent;
  restart_required: boolean;
  pending_changes: string[];
  components: Component[];
}

// -- the agent -------------------------------------------------------------------------------

/** What the agent is doing now (`GET /agent/activity`, and `event: activity` on the stream). */
export interface AgentActivity {
  state: "idle" | "listening" | "thinking" | "speaking" | "working" | "sleeping";
  since: Instant;
  replies: number;
  tasks: number;
  listening_rooms: string[];
  quiet: boolean;
}

/** A written follow-up of something said aloud: sent at `due_at` unless someone answers first. */
export interface UpcomingDelivery {
  about: string;
  delivery: string;
  person: { id: Id; name: string } | null;
  spoken_on: string; // `voice:salon`
  written_on: string; // `telegram:7`
  due_at: Instant;
}

export interface Initiative {
  quiet_hours: { start: string; end: string; timezone: string; active: boolean } | null;
  upcoming: UpcomingDelivery[];
}

// -- configuration -----------------------------------------------------------------------------

/** A JSON Schema as `/config/schema` sends it, with Nestor's `x-nestor` annotations. */
export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  additionalProperties?: boolean | JsonSchema;
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  enum?: (string | number)[];
  const?: unknown;
  default?: unknown;
  format?: string;
  writeOnly?: boolean;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  minLength?: number;
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  "x-nestor"?: {
    field?: string;
    title?: string;
    help?: string | null;
    secret?: boolean;
    /** a map whose values are secrets (MCP headers): each value is kept or replaced on its own */
    secret_values?: boolean;
    advanced?: boolean;
    group?: string;
  };
}

export interface ConfigSlot {
  family: string;
  many: boolean;
  required: boolean;
  title: string;
  kinds: Record<string, JsonSchema>;
}

export interface ConfigSchema {
  sections: Record<string, JsonSchema>;
  section_titles: Record<string, string>;
  slots: Record<string, ConfigSlot>;
}

/** A secret as the configuration shows it: never its value. */
export interface SecretShown {
  set: boolean;
  preview: string | null;
}

export type ConfigDocument = Record<string, unknown>;

export interface ConfigState {
  document: ConfigDocument;
  path: string;
  restart_required: boolean;
  pending_changes: string[];
}

export interface ConfigProblem {
  path: (string | number)[];
  code: string;
  message_id: string;
  args: Record<string, string | number>;
  message: string;
}

export interface ConfigChange {
  path: string;
  before: unknown;
  after: unknown;
  secret: boolean;
}

export interface ConfigDiff {
  added: ConfigChange[];
  removed: ConfigChange[];
  changed: ConfigChange[];
}

export interface ConfigPreview {
  valid: boolean;
  problems: ConfigProblem[];
  diff: ConfigDiff;
}

export interface ConfigWritten {
  diff: ConfigDiff;
  restart_required: boolean;
  pending_changes: string[];
}

export interface HistoryEntry {
  id: Id;
  at: Instant;
  size: number;
}

export interface HistoryDocument {
  id: Id;
  at: Instant;
  document: ConfigDocument;
}

export interface Secret {
  name: string;
  set: boolean;
  preview: string | null;
  used_by: string[]; // configuration paths that reference it
}

// -- errors ---------------------------------------------------------------------------------------

export interface ErrorBody {
  error: {
    code: string;
    message_id?: string;
    args?: Record<string, string | number>;
    message: string;
    problems?: ConfigProblem[] | null;
  };
}
