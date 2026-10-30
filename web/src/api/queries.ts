/** TanStack Query keys and options: screens ask for data through these, never through `api` directly. */
import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";
import { setCsrfToken } from "./client";
import { api } from "./resources";
import type { Id, JournalFilters, MemoryQuery } from "./types";

export const keys = {
  me: ["me"] as const,
  people: ["people"] as const,
  person: (id: Id) => ["people", id] as const,
  accounts: ["accounts"] as const,
  account: (id: Id) => ["accounts", id] as const,
  invitations: ["invitations"] as const,
  journal: (filters: JournalFilters) => ["journal", filters] as const,
  journalFacets: (filters: JournalFilters) => ["journal", "facets", filters] as const,
  journalEvent: (id: Id) => ["journal", "event", id] as const,
  system: ["system"] as const,
  connectors: ["connectors"] as const,
  connector: (kind: string) => ["connectors", kind] as const,
  connections: ["connections"] as const,
  connection: (id: Id) => ["connections", id] as const,
  satellites: ["satellites"] as const,
  satellite: (id: string) => ["satellites", id] as const,
  tasks: ["tasks"] as const,
  task: (id: Id) => ["tasks", id] as const,
  watches: ["watches"] as const,
  watch: (id: Id) => ["watches", id] as const,
  activity: ["agent", "activity"] as const,
  initiative: ["agent", "initiative"] as const,
  config: ["config"] as const,
  configSchema: ["config", "schema"] as const,
  configHistory: ["config", "history"] as const,
  configVersion: (id: Id) => ["config", "history", id] as const,
  secrets: ["config", "secrets"] as const,
  memories: (query: MemoryQuery) => ["memories", query] as const,
};

export const meQuery = queryOptions({
  queryKey: keys.me,
  queryFn: async ({ signal }) => {
    const me = await api.me(signal);
    setCsrfToken(me.csrf_token);
    return me;
  },
  staleTime: 60_000,
  retry: false,
});

export const peopleQuery = queryOptions({ queryKey: keys.people, queryFn: api.people, staleTime: 30_000 });
export const personQuery = (id: Id) => queryOptions({ queryKey: keys.person(id), queryFn: () => api.person(id) });
export const accountsQuery = queryOptions({ queryKey: keys.accounts, queryFn: api.accounts });
export const accountQuery = (id: Id) => queryOptions({ queryKey: keys.account(id), queryFn: () => api.account(id) });
export const invitationsQuery = queryOptions({ queryKey: keys.invitations, queryFn: api.invitations });

export const journalQuery = (filters: JournalFilters) =>
  infiniteQueryOptions({
    queryKey: keys.journal(filters),
    queryFn: ({ pageParam, signal }) => api.journal(filters, pageParam, signal),
    initialPageParam: undefined as Id | undefined,
    getNextPageParam: (last) => last.next ?? undefined,
  });

export const journalFacetsQuery = (filters: JournalFilters) =>
  queryOptions({
    queryKey: keys.journalFacets(filters),
    queryFn: ({ signal }) => api.journalFacets(filters, signal),
    placeholderData: (previous) => previous, // counts change in place instead of blinking
  });

/** A short list of the latest matching items (overview, related activity). */
export const journalLatestQuery = (filters: JournalFilters, limit = 8) =>
  queryOptions({
    queryKey: ["journal", "latest", filters, limit] as const,
    queryFn: ({ signal }) => api.journal(filters, undefined, signal, limit),
  });

export const journalEventQuery = (id: Id) =>
  queryOptions({ queryKey: keys.journalEvent(id), queryFn: () => api.journalEvent(id) });

export const systemQuery = queryOptions({ queryKey: keys.system, queryFn: api.system, refetchInterval: 15_000 });

export const connectorsQuery = queryOptions({ queryKey: keys.connectors, queryFn: api.connectors });
export const connectorQuery = (kind: string) =>
  queryOptions({ queryKey: keys.connector(kind), queryFn: () => api.connector(kind) });
export const connectionsQuery = queryOptions({ queryKey: keys.connections, queryFn: api.connections });
export const connectionQuery = (id: Id) =>
  queryOptions({ queryKey: keys.connection(id), queryFn: () => api.connection(id) });

export const satellitesQuery = queryOptions({
  queryKey: keys.satellites,
  queryFn: api.satellites,
  refetchInterval: 5_000, // a device asking to pair appears without reloading
});
export const satelliteQuery = (id: string) =>
  queryOptions({ queryKey: keys.satellite(id), queryFn: () => api.satellite(id) });
export const tasksQuery = queryOptions({ queryKey: keys.tasks, queryFn: api.tasks, refetchInterval: 5_000 });
export const taskQuery = (id: Id) =>
  queryOptions({
    queryKey: keys.task(id),
    queryFn: () => api.task(id),
    refetchInterval: (q) => (q.state.data && q.state.data.ended_at === null ? 5_000 : false),
  });
export const watchesQuery = queryOptions({ queryKey: keys.watches, queryFn: api.watches });
export const watchQuery = (id: Id) => queryOptions({ queryKey: keys.watch(id), queryFn: () => api.watch(id) });
export const memoriesQuery = (query: MemoryQuery) =>
  queryOptions({ queryKey: keys.memories(query), queryFn: () => api.memories(query) });

/** Kept current by the stream's `activity` events; fetched once, and again after a reconnect. */
export const activityQuery = queryOptions({
  queryKey: keys.activity,
  queryFn: ({ signal }) => api.activity(signal),
  staleTime: Number.POSITIVE_INFINITY,
});
export const initiativeQuery = queryOptions({
  queryKey: keys.initiative,
  queryFn: ({ signal }) => api.initiative(signal),
  refetchInterval: 60_000,
});

export const configSchemaQuery = queryOptions({
  queryKey: keys.configSchema,
  queryFn: api.configSchema,
  staleTime: Number.POSITIVE_INFINITY, // the installed plugins only change with a restart
});
export const configQuery = queryOptions({ queryKey: keys.config, queryFn: api.config });
export const configHistoryQuery = queryOptions({ queryKey: keys.configHistory, queryFn: api.configHistory });
export const configVersionQuery = (id: Id) =>
  queryOptions({ queryKey: keys.configVersion(id), queryFn: () => api.configVersion(id) });
export const secretsQuery = queryOptions({ queryKey: keys.secrets, queryFn: api.secrets });
