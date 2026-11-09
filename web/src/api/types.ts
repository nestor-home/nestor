/**
 * The API v1 as screens read it: names for the schemas generated from `web/openapi.json`
 * (`pnpm api:generate`). Nothing here restates a server shape, so a change of the API breaks the
 * screens that read it. Types the server never sends (the admin's own state) live with their screens.
 */
import type { components, paths } from "./schema.gen";

type S = components["schemas"];

export type Id = string;

// -- who is using the admin -----------------------------------------------------------------------

export type Role = S["Role"];
export type Scope = S["Scope"];
export type Account = S["AccountOut"];
export type Agent = S["AgentOut"];
export type Me = S["MeOut"];
export type Credentials = S["LoginIn"];
export type Invitation = S["InvitationOut"];
export type InvitationCreated = S["InvitationCreated"];
export type InvitationPreview = S["InvitationPreview"];
export type NewInvitation = S["InvitationIn"];
export type AcceptInvitation = Omit<S["InvitationAcceptIn"], "token">;
export type Languages = S["LanguagesOut"];

// -- the household --------------------------------------------------------------------------------

export type PersonRef = S["PersonRef"];
export type Presence = S["PresenceOut"];
export type Person = S["PersonOut"];
export type Voice = S["VoiceOut"];
export type VoiceRecording = S["RecordingOut"];
export type PhraseProblem = S["Problem"];
export type PhraseVerdict = S["PhraseOut"];
export type Heard = S["HeardOut"];

// -- server-owned texts and the journal -----------------------------------------------------------

export type Message = S["MessageOut"];
export type Rendered = S["ReasonOut"]; // a message and its text in the reader's language
export type Tone = S["Tone"];
export type Kind = S["Kind"];
export type EventLinks = S["LinksOut"];
export type JournalItem = S["JournalItem"];
export type JournalEvent = S["JournalEntryOut"];
export type JournalPage = S["JournalPage"];
export type JournalFacets = S["JournalFacets"];
export type Facet = S["FacetOut"];
export type JournalFilters = Omit<NonNullable<Query<"/api/v1/journal">>, "before" | "limit">;

// -- connectors and connections -------------------------------------------------------------------

export type AuthKind = S["AuthKind"];
export type ConnectionStatus = S["Status"];
export type Risk = S["Risk"];
export type Connector = S["ConnectorOut"];
export type Connection = S["ConnectionOut"];
export type ConnectionDetail = S["ConnectionDetail"];
export type Tool = S["ToolOut"];
export type OAuthClient = S["ClientIn"];
export type ConnectRequest = S["SecretsIn"];
export type ToolSettings = S["ConnectionSettingsIn"];

// -- the home -------------------------------------------------------------------------------------

export type Home = S["HomeOut"];
export type Granularity = S["Granularity"];
export type Suggest = S["Suggest"];

// -- satellites -----------------------------------------------------------------------------------

export type Capability = S["CapabilityOut"];
export type PairingMethodId = S["PairingMethod"];
export type PairingMethod = S["MethodOut"];
export type PairingMethods = S["MethodsOut"];
export type PairingRequest = S["PendingOut"];
export type Addition = S["AdditionOut"];
export type NewAddition = S["AdditionIn"];
export type StartedAddition = S["StartedOut"];
export type SatelliteUpdate = S["UpdateOut"];
export type Satellite = S["SatelliteOut"];
export type Satellites = S["SatellitesOut"];
export type Approval = Omit<S["ApprovalIn"], "pairing_id">;

// -- tasks, watches, memories ---------------------------------------------------------------------

export type TaskStatus = S["TaskStatus"];
export type Task = S["TaskOut"];
export type Tasks = S["TasksOut"];
export type Watch = S["WatchOut"];
export type Watches = S["WatchesOut"];
export type Day = S["Day"];
export type Schedule = S["ScheduleOut"];
export type PassedMessage = S["PassedMessageOut"];
export type Messages = S["MessagesOut"];
export type Confirmation = S["ConfirmationOut"];
export type Memory = S["MemoryOut"];
export type MemoryQuery = NonNullable<Query<"/api/v1/memories">>;

// -- system ---------------------------------------------------------------------------------------

export type Health = S["Health"];
export type Component = S["ComponentOut"];
export type ChangeKind = S["ChangeKind"];
export type Release = S["ReleaseOut"];
export type Installation = S["InstallKind"];
export type Updates = S["UpdatesOut"];
export type SystemInfo = S["SystemOut"];

// -- the agent ------------------------------------------------------------------------------------

export type AgentActivity = S["AgentActivityOut"];
export type UpcomingDelivery = S["ScheduledDeliveryOut"];
export type Initiative = S["InitiativeOut"];

// -- configuration --------------------------------------------------------------------------------

export type ModelType = S["ModelType"];
export type ConfigSlot = S["SlotOut"];
export type ConfigSchema = S["ConfigSchemaOut"];
export type ConfigDocument = S["ConfigOut"]["document"];
export type ConfigState = S["ConfigOut"];
export type ConfigProblem = S["ProblemOut"];
export type ConfigChange = S["ChangeOut"];
export type ConfigDiff = S["DiffOut"];
export type ConfigPreview = S["PreviewOut"];
export type ConfigWritten = S["WrittenOut"];
export type HistoryEntry = S["HistoryEntryOut"];
export type HistoryDocument = S["HistoryDocumentOut"];
export type Secret = S["SecretOut"];

// -- errors ---------------------------------------------------------------------------------------

export type ErrorCode = S["ErrorDetail"]["code"];
export type ErrorBody = S["ErrorOut"];

type Query<P extends keyof paths> = paths[P] extends { get: { parameters: { query?: infer Q } } } ? Q : never;
