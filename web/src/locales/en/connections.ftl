## Connections: connected accounts, the catalogue, connecting a service, one connection's pages.

conn-title = Connections
conn-intro = Tokens are encrypted and never shown to the model. Only enabled tools are used.
conn-connect-service = Connect a service
conn-tab-accounts = Connected accounts
conn-tab-catalogue = Catalogue

conn-empty = No account connected yet.
conn-empty-hint = A mailbox for watches, an MCP server for tools.
conn-open-catalogue = Open the catalogue
conn-calls-today = { $count ->
    [0] no call today
    [one] 1 call today
   *[other] { $count } calls today
}
conn-no-connector = No connector installed.
conn-feeds-watches = feeds watches
conn-accounts-count = { $count ->
    [one] 1 account
   *[other] { $count } accounts
}
conn-client-to-create = OAuth client missing
conn-connect-ellipsis = Connect…

conn-connect = Connect
conn-connecting = Connecting…
conn-redirecting = Redirecting to the service…
conn-connected = Connected
conn-connect-account = Connect an account
conn-oauth-consent = You will authorise access on the service's page.
conn-account-of = Account of
conn-account-of-hint = One person, or the whole household.
conn-field-optional = { $label } (optional)
conn-client-first = Register the OAuth client first.
conn-status-redirecting = [ redirecting… ]
conn-status-pending = [ in progress ]
conn-reconnect-note = The old access stays active until the new one works. Settings are kept.
conn-presets = Known servers
conn-credentials = Token or OAuth client
conn-redirect-uri-service = Redirect address to declare with the service
conn-field-kept = Left empty: kept from the account being reconnected.

conn-client-title = OAuth client
conn-client-registered = registered
conn-client-missing = missing
conn-client-id = Client ID
conn-client-why = Each household creates its own OAuth app with the provider: no secret is shared.
conn-redirect-uri = Redirect URI to declare with the provider
conn-redirect-uri-label = the redirect URI
conn-relayed = Without HTTPS, the provider goes through this public relay page, which sends you straight back here. The authorisation code passes through it, useless without this instance's key.
conn-client-replace-ellipsis = Replace the client…
conn-client-register-ellipsis = Register the client…
conn-client-replace-title = Replace the OAuth client
conn-client-register-title = Register the OAuth client
conn-client-replace-note = Only if it changed at the provider. Connected accounts keep working.
conn-client-saved = OAuth client registered: you can connect an account.
conn-client-id-field = Client ID
conn-client-secret-field = Client secret
conn-client-register = Register the client

conn-tools = Tools
conn-tools-saved = Tool settings saved.
conn-no-tools = No tools.
conn-confirm-writes = Ask for confirmation before writing
conn-confirm-writes-hint = Sensitive actions, such as sending, always ask.
conn-unsaved = ● unsaved changes

conn-sections = Connection sections
conn-tab-overview = Overview
conn-tab-activity = Activity
conn-tab-settings = Settings
conn-owner = account of { $name }
conn-connected-at = connected { $when }
conn-broken = { $assistant } can no longer use this account: its tools and watches are paused.
conn-reconnect = Reconnect
conn-reconnect-ellipsis = Reconnect…
conn-reconnect-hint = To switch account or password. Tool settings are kept.
conn-summary-owned = The { $service } account of { $name }.
conn-summary-household = { $service } for the whole household.
conn-summary-usage = { $count ->
    [0] { $assistant } has not used it today.
    [one] { $assistant } used it once today.
   *[other] { $assistant } used it { $count } times today.
}
conn-summary-usage-last = { $count ->
    [0] { $assistant } has not used it today; last time { $ago }.
    [one] { $assistant } used it once today, last { $ago }.
   *[other] { $assistant } used it { $count } times today, last { $ago }.
}
conn-summary-watches = { $count ->
    [one] It feeds 1 watch.
   *[other] It feeds { $count } watches.
}
conn-summary-tools = { $enabled } of { $total } tools on{ $writes ->
    [0] .
    [one] , 1 of which writes{ $confirm ->
        [yes] , with confirmation.
       *[no] , without confirmation.
    }
   *[other] , { $writes } of which write{ $confirm ->
        [yes] , with confirmation.
       *[no] , without confirmation.
    }
}
conn-latest-uses = Latest uses
conn-never-used = { $assistant } has not used it yet.
conn-no-activity = No activity yet.
conn-disconnected = Account { $account } disconnected.
conn-read-only = Your role does not allow changing this connection.
conn-disconnect = Disconnect
conn-disconnect-ellipsis = Disconnect…
conn-disconnect-hint = Revokes access at the provider when possible, then deletes the account's secrets.
conn-disconnect-title = Disconnect { $account }?
conn-disconnect-consequence = Its tools disappear and the watches that depend on it stop.
conn-account-connected = Account { $account } connected.

conn-failed-crumb = Failure
conn-failed-denied = Authorisation refused
conn-failed-denied-text = Nothing was connected.
conn-failed-expired = Authorisation request expired
conn-failed-expired-text = More than ten minutes passed. Start again.
conn-failed-unknown = Unknown authorisation request
conn-failed-unknown-text = It was not started from this session. Start again from the catalogue.
conn-failed-exchange = Code refused by the service
conn-failed-exchange-text = Check the OAuth client, then start again.
conn-failed-other = The service returned an error
conn-failed-other-text = Error: “{ $error }”.
conn-failed-no-code = no code
conn-failed-retry = Start again
conn-failed-back = Back to connections
