/** One function per API operation, on the generated client: screens read the answers as the API sends them. */
import { client, unwrap } from "./client";
import type {
  AcceptInvitation,
  Approval,
  ConfigDocument,
  Connection,
  Connector,
  ConnectRequest,
  Credentials,
  Id,
  JournalFilters,
  MemoryQuery,
  NewAddition,
  NewInvitation,
  OAuthClient,
  Role,
  ToolSettings,
} from "./types";

/** A WAV file as the body of a request: sent as it is, not as JSON. */
const wav = (audio: ArrayBuffer) => ({
  body: audio as unknown as string,
  bodySerializer: (body: unknown) => body as ArrayBuffer,
  headers: { "Content-Type": "audio/wav" },
});

/** An operation whose answer the screens do not read. */
const done = (call: Parameters<typeof unwrap>[0]): Promise<void> => unwrap(call).then(() => undefined);

/** How connecting ends: on the provider's consent page, or connected at once. */
export type ConnectResult = { kind: "redirect"; url: string } | { kind: "connected"; connection: Connection };

/** What the accounts screen changes: one of the role, or whether it may sign in. */
export type AccountChange = { role?: Role; disabled?: boolean };

export const api = {
  // session
  me: (signal?: AbortSignal) => unwrap(client.GET("/api/v1/me", { signal })),
  login: (body: Credentials) => unwrap(client.POST("/api/v1/session", { body })),
  logout: () => done(client.DELETE("/api/v1/session")),
  setLocale: (locale: string | null) => unwrap(client.PUT("/api/v1/me/locale", { body: { locale } })),
  invitation: (token: string) => unwrap(client.POST("/api/v1/invitations/inspect", { body: { token } })),
  acceptInvitation: (token: string, body: AcceptInvitation) =>
    unwrap(client.POST("/api/v1/invitations/accept", { body: { token, ...body } })),

  // accounts
  accounts: () => unwrap(client.GET("/api/v1/accounts")),
  account: (id: Id) => unwrap(client.GET("/api/v1/accounts/{account_id}", { params: { path: { account_id: id } } })),
  invitations: () => unwrap(client.GET("/api/v1/invitations")),
  invite: (body: NewInvitation) => unwrap(client.POST("/api/v1/invitations", { body })),
  revokeInvitation: (id: Id) =>
    done(client.DELETE("/api/v1/invitations/{invitation_id}", { params: { path: { invitation_id: id } } })),
  changeAccount: async (id: Id, change: AccountChange) => {
    const path = { params: { path: { account_id: id } } };
    if (change.role)
      return await unwrap(client.PUT("/api/v1/accounts/{account_id}/role", { ...path, body: { role: change.role } }));
    if (change.disabled) return await unwrap(client.POST("/api/v1/accounts/{account_id}/disable", path));
    return await unwrap(client.POST("/api/v1/accounts/{account_id}/enable", path));
  },

  // household
  people: () => unwrap(client.GET("/api/v1/household/people")),
  person: (id: Id) =>
    unwrap(client.GET("/api/v1/household/people/{person_id}", { params: { path: { person_id: id } } })),

  // journal
  journal: (filters: JournalFilters, before?: number, signal?: AbortSignal, limit?: number) =>
    unwrap(client.GET("/api/v1/journal", { params: { query: { ...filters, before, limit } }, signal })),
  journalFacets: (filters: JournalFilters, signal?: AbortSignal) =>
    unwrap(client.GET("/api/v1/journal/facets", { params: { query: filters }, signal })),
  journalEvent: (position: number) =>
    unwrap(client.GET("/api/v1/journal/{position}", { params: { path: { position } } })),

  // system
  system: () => unwrap(client.GET("/api/v1/system")),
  updates: () => unwrap(client.GET("/api/v1/system/updates")),
  /** Installs the newest release where Nestor runs, then restarts on it: a person's confirmed action. */
  installUpdate: (version: string) =>
    unwrap(client.POST("/api/v1/system/updates/install", { body: { version, confirm: true } })),
  /** Asks for a restart: always a person's explicit, confirmed action. */
  restart: () => done(client.POST("/api/v1/system/restart", { body: { confirm: true } })),
  /** Whether the instance answers at all (outside the API: it is up before a session is). */
  health: async (signal?: AbortSignal) => {
    try {
      return (await globalThis.fetch("/health", { cache: "no-store", signal })).ok;
    } catch {
      return false;
    }
  },

  // the agent
  activity: (signal?: AbortSignal) => unwrap(client.GET("/api/v1/agent/activity", { signal })),
  initiative: (signal?: AbortSignal) => unwrap(client.GET("/api/v1/agent/initiative", { signal })),

  // configuration
  configSchema: () => unwrap(client.GET("/api/v1/config/schema")),
  config: () => unwrap(client.GET("/api/v1/config")),
  previewConfig: (document: ConfigDocument, signal?: AbortSignal) =>
    unwrap(client.POST("/api/v1/config/preview", { body: { document }, signal })),
  writeConfig: (document: ConfigDocument) => unwrap(client.PUT("/api/v1/config", { body: { document } })),
  configHistory: () => unwrap(client.GET("/api/v1/config/history")),
  configVersion: (id: Id) =>
    unwrap(client.GET("/api/v1/config/history/{entry_id}", { params: { path: { entry_id: id } } })),
  restoreConfig: (id: Id) =>
    unwrap(client.POST("/api/v1/config/history/{entry_id}/restore", { params: { path: { entry_id: id } } })),
  secrets: () => unwrap(client.GET("/api/v1/config/secrets")),
  setSecret: (name: string, value: string) =>
    unwrap(client.PUT("/api/v1/config/secrets/{name}", { params: { path: { name } }, body: { value } })),
  deleteSecret: (name: string, force = false) =>
    done(client.DELETE("/api/v1/config/secrets/{name}", { params: { path: { name }, query: { force } } })),

  // connectors and connections
  connectors: () => unwrap(client.GET("/api/v1/connectors")),
  connector: (kind: string) => unwrap(client.GET("/api/v1/connectors/{kind}", { params: { path: { kind } } })),
  setClient: (kind: string, body: OAuthClient) =>
    unwrap(client.PUT("/api/v1/connectors/{kind}/client", { params: { path: { kind } }, body })),
  /** OAuth answers with the provider's consent page; other connectors connect at once. */
  connect: async (kind: string, request: ConnectRequest, auth: Connector["auth"]): Promise<ConnectResult> => {
    const path = { params: { path: { kind } } };
    if (auth === "oauth2") {
      const begun = await unwrap(
        client.POST("/api/v1/connectors/{kind}/authorizations", {
          ...path,
          body: { person: request.person, replaces: request.replaces },
        }),
      );
      return { kind: "redirect", url: begun.authorize_url };
    }
    const made = await unwrap(client.POST("/api/v1/connectors/{kind}/connections", { ...path, body: request }));
    return { kind: "connected", connection: made };
  },
  connections: () => unwrap(client.GET("/api/v1/connections")),
  connection: (id: Id) =>
    unwrap(client.GET("/api/v1/connections/{connection_id}", { params: { path: { connection_id: id } } })),
  configureTools: (id: Id, body: ToolSettings) =>
    unwrap(client.PATCH("/api/v1/connections/{connection_id}", { params: { path: { connection_id: id } }, body })),
  disconnect: (id: Id) =>
    done(client.DELETE("/api/v1/connections/{connection_id}", { params: { path: { connection_id: id } } })),

  // satellites
  satellites: () => unwrap(client.GET("/api/v1/satellites")),
  pairingMethods: () => unwrap(client.GET("/api/v1/satellites/pairing-methods")),
  startAddition: (body: NewAddition) => unwrap(client.POST("/api/v1/satellites/additions", { body })),
  addition: (id: Id, signal?: AbortSignal) =>
    unwrap(client.GET("/api/v1/satellites/additions/{addition_id}", { params: { path: { addition_id: id } }, signal })),
  cancelAddition: (id: Id) =>
    done(client.DELETE("/api/v1/satellites/additions/{addition_id}", { params: { path: { addition_id: id } } })),
  identifyPending: (pairing: Id) =>
    done(
      client.POST("/api/v1/satellites/pending/{pairing_id}/identify", { params: { path: { pairing_id: pairing } } }),
    ),
  identify: (device: string) =>
    done(client.POST("/api/v1/satellites/{device_id}/identify", { params: { path: { device_id: device } } })),
  /** Asks a connected satellite to install the newer version it reported; answers that version. */
  updateSatellite: async (device: string) =>
    (await unwrap(client.POST("/api/v1/satellites/{device_id}/update", { params: { path: { device_id: device } } })))
      .version,
  satellite: (device: string) =>
    unwrap(client.GET("/api/v1/satellites/{device_id}", { params: { path: { device_id: device } } })),
  approve: (pairing: Id, body: Approval) =>
    unwrap(client.POST("/api/v1/satellites/approvals", { body: { ...body, pairing_id: pairing } })),
  revoke: (device: string) =>
    done(client.DELETE("/api/v1/satellites/{device_id}", { params: { path: { device_id: device } } })),

  // voices
  voice: (person: Id) =>
    unwrap(client.GET("/api/v1/household/people/{person_id}/voice", { params: { path: { person_id: person } } })),
  startRecording: (person: Id, learning: boolean) =>
    unwrap(
      client.POST("/api/v1/household/people/{person_id}/voice/recording", {
        params: { path: { person_id: person } },
        body: { learning },
      }),
    ),
  sayPhrase: (recording: Id, phrase: number, audio: ArrayBuffer) =>
    unwrap(
      client.PUT("/api/v1/voice/recordings/{recording_id}/phrases/{phrase}", {
        params: { path: { recording_id: recording, phrase } },
        ...wav(audio),
      }),
    ),
  finishRecording: (recording: Id) =>
    unwrap(
      client.POST("/api/v1/voice/recordings/{recording_id}/finish", { params: { path: { recording_id: recording } } }),
    ),
  abandonRecording: (recording: Id) =>
    done(client.DELETE("/api/v1/voice/recordings/{recording_id}", { params: { path: { recording_id: recording } } })),
  hear: (audio: ArrayBuffer) => unwrap(client.POST("/api/v1/voice/hear", wav(audio))),
  setVoiceLearning: (person: Id, learning: boolean) =>
    unwrap(
      client.PUT("/api/v1/household/people/{person_id}/voice/learning", {
        params: { path: { person_id: person } },
        body: { learning },
      }),
    ),
  forgetVoice: (person: Id, learnedOnly = false) =>
    unwrap(
      client.DELETE("/api/v1/household/people/{person_id}/voice", {
        params: { path: { person_id: person }, query: { learned_only: learnedOnly } },
      }),
    ),

  // tasks, watches, memories
  tasks: () => unwrap(client.GET("/api/v1/tasks")),
  task: (id: Id) => unwrap(client.GET("/api/v1/tasks/{task_id}", { params: { path: { task_id: id } } })),
  cancelTask: (id: Id) => done(client.POST("/api/v1/tasks/{task_id}/cancel", { params: { path: { task_id: id } } })),
  watches: () => unwrap(client.GET("/api/v1/watches")),
  watch: (id: Id) => unwrap(client.GET("/api/v1/watches/{watch_id}", { params: { path: { watch_id: id } } })),
  cancelWatch: (id: Id) =>
    done(client.POST("/api/v1/watches/{watch_id}/cancel", { params: { path: { watch_id: id } } })),
  schedules: () => unwrap(client.GET("/api/v1/schedules")),
  cancelSchedule: (id: Id) =>
    done(client.POST("/api/v1/schedules/{schedule_id}/cancel", { params: { path: { schedule_id: id } } })),
  messages: () => unwrap(client.GET("/api/v1/messages")),

  // the admin's chat (the answer's stream is read in `features/chat/live.ts`)
  chats: () => unwrap(client.GET("/api/v1/chats")),
  mentions: () => unwrap(client.GET("/api/v1/chats/mentions")),
  chat: (chat: Id) => unwrap(client.GET("/api/v1/chats/{chat}", { params: { path: { chat } } })),
  stopChat: (chat: Id) => done(client.POST("/api/v1/chats/{chat}/stop", { params: { path: { chat } } })),
  confirmations: () => unwrap(client.GET("/api/v1/confirmations")),
  answerConfirmation: (id: Id, approved: boolean) =>
    unwrap(
      client.POST("/api/v1/confirmations/{confirmation_id}/answer", {
        params: { path: { confirmation_id: id } },
        body: { approved },
      }),
    ),
  home: () => unwrap(client.GET("/api/v1/home")),
  memories: (query: MemoryQuery) => unwrap(client.GET("/api/v1/memories", { params: { query } })),
  correctMemory: (id: Id, text: string) =>
    unwrap(client.PATCH("/api/v1/memories/{memory_id}", { params: { path: { memory_id: id } }, body: { text } })),
  forgetMemory: (id: Id) =>
    done(client.DELETE("/api/v1/memories/{memory_id}", { params: { path: { memory_id: id } } })),
};

export type Api = typeof api;
