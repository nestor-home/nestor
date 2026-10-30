/** One function per API operation, on the generated client; answers adapted to what screens read. */
import * as adapt from "./adapt";
import { client, unwrap } from "./client";
import type {
  AcceptInvitation,
  Account,
  AccountChange,
  Approval,
  ConnectionDetail,
  Connector,
  ConnectRequest,
  ConnectResult,
  Credentials,
  Id,
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
  NewInvitation,
  OAuthClient,
  Person,
  Satellite,
  Satellites,
  SystemInfo,
  Tasks,
  ToolSettings,
  Watches,
} from "./types";

/** Filters as query parameters: several kinds travel comma-separated. */
export function journalQuery({ kinds, ...rest }: JournalFilters) {
  return { ...rest, kinds: kinds?.length ? kinds.join(",") : undefined };
}

const invitationLink = (url: string) =>
  url.startsWith("http") ? url : new URL(url, window.location.origin).toString();

export const api = {
  // session
  me: async (signal?: AbortSignal): Promise<Me> => adapt.me(await unwrap(client.GET("/api/v1/me", { signal }))),
  login: async (body: Credentials): Promise<Me> => adapt.me(await unwrap(client.POST("/api/v1/session", { body }))),
  logout: (): Promise<void> => unwrap(client.DELETE("/api/v1/session")).then(() => undefined),
  setLocale: async (locale: string | null): Promise<Me> =>
    adapt.me(await unwrap(client.PUT("/api/v1/me/locale", { body: { locale } }))),
  invitation: async (token: string): Promise<InvitationPreview> =>
    adapt.preview(await unwrap(client.POST("/api/v1/invitations/inspect", { body: { token } }))),
  acceptInvitation: async (token: string, body: AcceptInvitation): Promise<Me> =>
    adapt.me(await unwrap(client.POST("/api/v1/invitations/accept", { body: { token, ...body } }))),

  // accounts
  accounts: async (): Promise<Account[]> => (await unwrap(client.GET("/api/v1/accounts"))).map(adapt.account),
  invitations: async (): Promise<Invitation[]> =>
    (await unwrap(client.GET("/api/v1/invitations"))).map(adapt.invitation),
  invite: async (body: NewInvitation): Promise<InvitationCreated> => {
    const created = await unwrap(client.POST("/api/v1/invitations", { body }));
    return { invitation: adapt.invitation(created.invitation), link: invitationLink(created.url) };
  },
  revokeInvitation: (id: Id): Promise<void> =>
    unwrap(client.DELETE("/api/v1/invitations/{invitation_id}", { params: { path: { invitation_id: id } } })).then(
      () => undefined,
    ),
  changeAccount: async (id: Id, change: AccountChange): Promise<Account> => {
    const path = { params: { path: { account_id: id } } };
    if (change.role)
      return adapt.account(
        await unwrap(client.PUT("/api/v1/accounts/{account_id}/role", { ...path, body: { role: change.role } })),
      );
    if (change.disabled) return adapt.account(await unwrap(client.POST("/api/v1/accounts/{account_id}/disable", path)));
    return adapt.account(await unwrap(client.POST("/api/v1/accounts/{account_id}/enable", path)));
  },

  // household
  people: async (): Promise<Person[]> => (await unwrap(client.GET("/api/v1/household/people"))).map(adapt.person),

  // journal
  journal: async (filters: JournalFilters, before?: Id, signal?: AbortSignal, limit?: number): Promise<JournalPage> => {
    const page = await unwrap(
      client.GET("/api/v1/journal", {
        params: { query: { ...journalQuery(filters), before: before ? Number(before) : undefined, limit } },
        signal,
      }),
    );
    return {
      items: page.items.map(adapt.journalItem),
      next: page.next_before === null ? null : String(page.next_before),
    };
  },
  journalFacets: async (filters: JournalFilters, signal?: AbortSignal): Promise<JournalFacets> =>
    adapt.facets(
      await unwrap(client.GET("/api/v1/journal/facets", { params: { query: journalQuery(filters) }, signal })),
    ),
  journalEvent: async (position: Id): Promise<JournalEvent> =>
    adapt.journalEvent(
      await unwrap(client.GET("/api/v1/journal/{position}", { params: { path: { position: Number(position) } } })),
    ),

  // system
  system: async (): Promise<SystemInfo> => adapt.system(await unwrap(client.GET("/api/v1/system"))),

  // connectors and connections
  connectors: async (): Promise<Connector[]> => (await unwrap(client.GET("/api/v1/connectors"))).map(adapt.connector),
  connector: async (kind: string): Promise<Connector> =>
    adapt.connector(await unwrap(client.GET("/api/v1/connectors/{kind}", { params: { path: { kind } } }))),
  setClient: async (kind: string, body: OAuthClient): Promise<Connector> =>
    adapt.connector(await unwrap(client.PUT("/api/v1/connectors/{kind}/client", { params: { path: { kind } }, body }))),
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
    return { kind: "connected", connection: adapt.connection(made) };
  },
  connections: async () => (await unwrap(client.GET("/api/v1/connections"))).map(adapt.connection),
  connection: async (id: Id): Promise<ConnectionDetail> =>
    adapt.connectionDetail(
      await unwrap(client.GET("/api/v1/connections/{connection_id}", { params: { path: { connection_id: id } } })),
    ),
  configureTools: async (id: Id, body: ToolSettings): Promise<ConnectionDetail> =>
    adapt.connectionDetail(
      await unwrap(
        client.PATCH("/api/v1/connections/{connection_id}", { params: { path: { connection_id: id } }, body }),
      ),
    ),
  disconnect: (id: Id): Promise<void> =>
    unwrap(client.DELETE("/api/v1/connections/{connection_id}", { params: { path: { connection_id: id } } })).then(
      () => undefined,
    ),

  // satellites
  satellites: async (): Promise<Satellites> => {
    const all = await unwrap(client.GET("/api/v1/satellites"));
    const now = Date.now();
    return { pending: all.pending.map((p) => adapt.pending(p, now)), paired: all.paired.map(adapt.satellite) };
  },
  approve: async (pairing: Id, body: Approval): Promise<Satellite> =>
    adapt.satellite(
      await unwrap(client.POST("/api/v1/satellites/approvals", { body: { ...body, pairing_id: pairing } })),
    ),
  revoke: (device: string): Promise<void> =>
    unwrap(client.DELETE("/api/v1/satellites/{device_id}", { params: { path: { device_id: device } } })).then(
      () => undefined,
    ),

  // tasks, watches, memories
  tasks: async (): Promise<Tasks> => {
    const all = await unwrap(client.GET("/api/v1/tasks"));
    return { running: all.running.map(adapt.task), recent: all.recent.map(adapt.task) };
  },
  cancelTask: (id: Id): Promise<void> =>
    unwrap(client.POST("/api/v1/tasks/{task_id}/cancel", { params: { path: { task_id: id } } })).then(() => undefined),
  watches: async (): Promise<Watches> => {
    const all = await unwrap(client.GET("/api/v1/watches"));
    return { watches: all.watches.map(adapt.watch), sources: all.kinds };
  },
  cancelWatch: (id: Id): Promise<void> =>
    unwrap(client.POST("/api/v1/watches/{watch_id}/cancel", { params: { path: { watch_id: id } } })).then(
      () => undefined,
    ),
  memories: async (query: MemoryQuery): Promise<Memory[]> =>
    (await unwrap(client.GET("/api/v1/memories", { params: { query } }))).map(adapt.memory),
  correctMemory: async (id: Id, text: string): Promise<Memory> =>
    adapt.memory(
      await unwrap(
        client.PATCH("/api/v1/memories/{memory_id}", { params: { path: { memory_id: id } }, body: { text } }),
      ),
    ),
  forgetMemory: (id: Id): Promise<void> =>
    unwrap(client.DELETE("/api/v1/memories/{memory_id}", { params: { path: { memory_id: id } } })).then(
      () => undefined,
    ),
};

export type Api = typeof api;
