/** One function per API operation, on the generated client: screens read the answers as the API sends them. */
import { client, unwrap } from "./client";
import type {
  AcceptInvitation,
  Account,
  Addition,
  AgentActivity,
  Approval,
  ConfigDocument,
  ConfigPreview,
  ConfigSchema,
  ConfigState,
  ConfigWritten,
  Connection,
  ConnectionDetail,
  Connector,
  ConnectRequest,
  ConnectResult,
  Credentials,
  Heard,
  HistoryDocument,
  HistoryEntry,
  Id,
  Initiative,
  Invitation,
  InvitationCreated,
  InvitationPreview,
  JournalEvent,
  JournalFacets,
  JournalFilters,
  JournalPage,
  Me,
  Memory,
  MemoryQuery,
  NewAddition,
  NewInvitation,
  OAuthClient,
  PairingMethods,
  Person,
  PhraseVerdict,
  Role,
  Satellite,
  Satellites,
  Secret,
  StartedAddition,
  SystemInfo,
  Task,
  Tasks,
  ToolSettings,
  Updates,
  Voice,
  VoiceRecording,
  Watch,
  Watches,
} from "./types";

/** A WAV file as the body of a request: sent as it is, not as JSON. */
const wav = (audio: ArrayBuffer) => ({
  body: audio as unknown as string,
  bodySerializer: (body: unknown) => body as ArrayBuffer,
  headers: { "Content-Type": "audio/wav" },
});

/** What the accounts screen changes: one of the role, or whether it may sign in. */
export type AccountChange = { role?: Role; disabled?: boolean };

export const api = {
  // session
  me: (signal?: AbortSignal): Promise<Me> => unwrap(client.GET("/api/v1/me", { signal })),
  login: (body: Credentials): Promise<Me> => unwrap(client.POST("/api/v1/session", { body })),
  logout: (): Promise<void> => unwrap(client.DELETE("/api/v1/session")).then(() => undefined),
  setLocale: (locale: string | null): Promise<Me> => unwrap(client.PUT("/api/v1/me/locale", { body: { locale } })),
  invitation: (token: string): Promise<InvitationPreview> =>
    unwrap(client.POST("/api/v1/invitations/inspect", { body: { token } })),
  acceptInvitation: (token: string, body: AcceptInvitation): Promise<Me> =>
    unwrap(client.POST("/api/v1/invitations/accept", { body: { token, ...body } })),

  // accounts
  accounts: (): Promise<Account[]> => unwrap(client.GET("/api/v1/accounts")),
  account: (id: Id): Promise<Account> =>
    unwrap(client.GET("/api/v1/accounts/{account_id}", { params: { path: { account_id: id } } })),
  invitations: (): Promise<Invitation[]> => unwrap(client.GET("/api/v1/invitations")),
  invite: (body: NewInvitation): Promise<InvitationCreated> => unwrap(client.POST("/api/v1/invitations", { body })),
  revokeInvitation: (id: Id): Promise<void> =>
    unwrap(client.DELETE("/api/v1/invitations/{invitation_id}", { params: { path: { invitation_id: id } } })).then(
      () => undefined,
    ),
  changeAccount: async (id: Id, change: AccountChange): Promise<Account> => {
    const path = { params: { path: { account_id: id } } };
    if (change.role)
      return await unwrap(client.PUT("/api/v1/accounts/{account_id}/role", { ...path, body: { role: change.role } }));
    if (change.disabled) return await unwrap(client.POST("/api/v1/accounts/{account_id}/disable", path));
    return await unwrap(client.POST("/api/v1/accounts/{account_id}/enable", path));
  },

  // household
  people: (): Promise<Person[]> => unwrap(client.GET("/api/v1/household/people")),
  person: (id: Id): Promise<Person> =>
    unwrap(client.GET("/api/v1/household/people/{person_id}", { params: { path: { person_id: id } } })),

  // journal
  journal: (filters: JournalFilters, before?: number, signal?: AbortSignal, limit?: number): Promise<JournalPage> =>
    unwrap(client.GET("/api/v1/journal", { params: { query: { ...filters, before, limit } }, signal })),
  journalFacets: (filters: JournalFilters, signal?: AbortSignal): Promise<JournalFacets> =>
    unwrap(client.GET("/api/v1/journal/facets", { params: { query: filters }, signal })),
  journalEvent: (position: number): Promise<JournalEvent> =>
    unwrap(client.GET("/api/v1/journal/{position}", { params: { path: { position } } })),

  // system
  system: (): Promise<SystemInfo> => unwrap(client.GET("/api/v1/system")),
  updates: (): Promise<Updates> => unwrap(client.GET("/api/v1/system/updates")),
  /** Installs the newest release where Nestor runs, then restarts on it: a person's confirmed action. */
  installUpdate: (version: string): Promise<Updates> =>
    unwrap(client.POST("/api/v1/system/updates/install", { body: { version, confirm: true } })),
  /** Asks for a restart: always a person's explicit, confirmed action. */
  restart: (): Promise<void> =>
    unwrap(client.POST("/api/v1/system/restart", { body: { confirm: true } })).then(() => undefined),
  /** Whether the instance answers at all (outside the API: it is up before a session is). */
  health: async (signal?: AbortSignal): Promise<boolean> => {
    try {
      return (await globalThis.fetch("/health", { cache: "no-store", signal })).ok;
    } catch {
      return false;
    }
  },

  // the agent
  activity: (signal?: AbortSignal): Promise<AgentActivity> => unwrap(client.GET("/api/v1/agent/activity", { signal })),
  initiative: (signal?: AbortSignal): Promise<Initiative> => unwrap(client.GET("/api/v1/agent/initiative", { signal })),

  // configuration
  configSchema: (): Promise<ConfigSchema> => unwrap(client.GET("/api/v1/config/schema")),
  config: (): Promise<ConfigState> => unwrap(client.GET("/api/v1/config")),
  previewConfig: (document: ConfigDocument, signal?: AbortSignal): Promise<ConfigPreview> =>
    unwrap(client.POST("/api/v1/config/preview", { body: { document }, signal })),
  writeConfig: (document: ConfigDocument): Promise<ConfigWritten> =>
    unwrap(client.PUT("/api/v1/config", { body: { document } })),
  configHistory: (): Promise<HistoryEntry[]> => unwrap(client.GET("/api/v1/config/history")),
  configVersion: (id: Id): Promise<HistoryDocument> =>
    unwrap(client.GET("/api/v1/config/history/{entry_id}", { params: { path: { entry_id: id } } })),
  restoreConfig: (id: Id): Promise<ConfigWritten> =>
    unwrap(client.POST("/api/v1/config/history/{entry_id}/restore", { params: { path: { entry_id: id } } })),
  secrets: (): Promise<Secret[]> => unwrap(client.GET("/api/v1/config/secrets")),
  setSecret: (name: string, value: string): Promise<Secret> =>
    unwrap(client.PUT("/api/v1/config/secrets/{name}", { params: { path: { name } }, body: { value } })),
  deleteSecret: (name: string, force = false): Promise<void> =>
    unwrap(client.DELETE("/api/v1/config/secrets/{name}", { params: { path: { name }, query: { force } } })).then(
      () => undefined,
    ),

  // connectors and connections
  connectors: (): Promise<Connector[]> => unwrap(client.GET("/api/v1/connectors")),
  connector: (kind: string): Promise<Connector> =>
    unwrap(client.GET("/api/v1/connectors/{kind}", { params: { path: { kind } } })),
  setClient: (kind: string, body: OAuthClient): Promise<Connector> =>
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
  connections: (): Promise<Connection[]> => unwrap(client.GET("/api/v1/connections")),
  connection: (id: Id): Promise<ConnectionDetail> =>
    unwrap(client.GET("/api/v1/connections/{connection_id}", { params: { path: { connection_id: id } } })),
  configureTools: (id: Id, body: ToolSettings): Promise<ConnectionDetail> =>
    unwrap(client.PATCH("/api/v1/connections/{connection_id}", { params: { path: { connection_id: id } }, body })),
  disconnect: (id: Id): Promise<void> =>
    unwrap(client.DELETE("/api/v1/connections/{connection_id}", { params: { path: { connection_id: id } } })).then(
      () => undefined,
    ),

  // satellites
  satellites: (): Promise<Satellites> => unwrap(client.GET("/api/v1/satellites")),
  pairingMethods: (): Promise<PairingMethods> => unwrap(client.GET("/api/v1/satellites/pairing-methods")),
  startAddition: (body: NewAddition): Promise<StartedAddition> =>
    unwrap(client.POST("/api/v1/satellites/additions", { body })),
  addition: (id: Id, signal?: AbortSignal): Promise<Addition> =>
    unwrap(client.GET("/api/v1/satellites/additions/{addition_id}", { params: { path: { addition_id: id } }, signal })),
  cancelAddition: (id: Id): Promise<void> =>
    unwrap(client.DELETE("/api/v1/satellites/additions/{addition_id}", { params: { path: { addition_id: id } } })).then(
      () => undefined,
    ),
  identifyPending: (pairing: Id): Promise<void> =>
    unwrap(
      client.POST("/api/v1/satellites/pending/{pairing_id}/identify", { params: { path: { pairing_id: pairing } } }),
    ).then(() => undefined),
  identify: (device: string): Promise<void> =>
    unwrap(client.POST("/api/v1/satellites/{device_id}/identify", { params: { path: { device_id: device } } })).then(
      () => undefined,
    ),
  /** Asks a connected satellite to install the newer version it reported; answers that version. */
  updateSatellite: async (device: string): Promise<string> =>
    (await unwrap(client.POST("/api/v1/satellites/{device_id}/update", { params: { path: { device_id: device } } })))
      .version,
  satellite: (device: string): Promise<Satellite> =>
    unwrap(client.GET("/api/v1/satellites/{device_id}", { params: { path: { device_id: device } } })),
  approve: (pairing: Id, body: Approval): Promise<Satellite> =>
    unwrap(client.POST("/api/v1/satellites/approvals", { body: { ...body, pairing_id: pairing } })),
  revoke: (device: string): Promise<void> =>
    unwrap(client.DELETE("/api/v1/satellites/{device_id}", { params: { path: { device_id: device } } })).then(
      () => undefined,
    ),

  // voices
  voice: (person: Id): Promise<Voice> =>
    unwrap(client.GET("/api/v1/household/people/{person_id}/voice", { params: { path: { person_id: person } } })),
  startRecording: (person: Id, learning: boolean): Promise<VoiceRecording> =>
    unwrap(
      client.POST("/api/v1/household/people/{person_id}/voice/recording", {
        params: { path: { person_id: person } },
        body: { learning },
      }),
    ),
  sayPhrase: (recording: Id, phrase: number, audio: ArrayBuffer): Promise<PhraseVerdict> =>
    unwrap(
      client.PUT("/api/v1/voice/recordings/{recording_id}/phrases/{phrase}", {
        params: { path: { recording_id: recording, phrase } },
        ...wav(audio),
      }),
    ),
  finishRecording: (recording: Id): Promise<Voice> =>
    unwrap(
      client.POST("/api/v1/voice/recordings/{recording_id}/finish", { params: { path: { recording_id: recording } } }),
    ),
  abandonRecording: (recording: Id): Promise<void> =>
    unwrap(
      client.DELETE("/api/v1/voice/recordings/{recording_id}", { params: { path: { recording_id: recording } } }),
    ).then(() => undefined),
  hear: (audio: ArrayBuffer): Promise<Heard> => unwrap(client.POST("/api/v1/voice/hear", wav(audio))),
  setVoiceLearning: (person: Id, learning: boolean): Promise<Voice> =>
    unwrap(
      client.PUT("/api/v1/household/people/{person_id}/voice/learning", {
        params: { path: { person_id: person } },
        body: { learning },
      }),
    ),
  forgetVoice: (person: Id, learnedOnly = false): Promise<Voice> =>
    unwrap(
      client.DELETE("/api/v1/household/people/{person_id}/voice", {
        params: { path: { person_id: person }, query: { learned_only: learnedOnly } },
      }),
    ),

  // tasks, watches, memories
  tasks: (): Promise<Tasks> => unwrap(client.GET("/api/v1/tasks")),
  task: (id: Id): Promise<Task> => unwrap(client.GET("/api/v1/tasks/{task_id}", { params: { path: { task_id: id } } })),
  cancelTask: (id: Id): Promise<void> =>
    unwrap(client.POST("/api/v1/tasks/{task_id}/cancel", { params: { path: { task_id: id } } })).then(() => undefined),
  watches: (): Promise<Watches> => unwrap(client.GET("/api/v1/watches")),
  watch: (id: Id): Promise<Watch> =>
    unwrap(client.GET("/api/v1/watches/{watch_id}", { params: { path: { watch_id: id } } })),
  cancelWatch: (id: Id): Promise<void> =>
    unwrap(client.POST("/api/v1/watches/{watch_id}/cancel", { params: { path: { watch_id: id } } })).then(
      () => undefined,
    ),
  memories: (query: MemoryQuery): Promise<Memory[]> => unwrap(client.GET("/api/v1/memories", { params: { query } })),
  correctMemory: (id: Id, text: string): Promise<Memory> =>
    unwrap(client.PATCH("/api/v1/memories/{memory_id}", { params: { path: { memory_id: id } }, body: { text } })),
  forgetMemory: (id: Id): Promise<void> =>
    unwrap(client.DELETE("/api/v1/memories/{memory_id}", { params: { path: { memory_id: id } } })).then(
      () => undefined,
    ),
};

export type Api = typeof api;
