## Connections: connected accounts, the catalogue, connecting a service, one connection's pages.

conn-title = Connections
conn-intro = Tokens are encrypted and never shown to the model; { $assistant } only uses the tools you switch on.
conn-connect-service = Connect a service
conn-tab-accounts = Connected accounts
conn-tab-catalogue = Catalogue

conn-empty = No account connected yet.
conn-empty-hint = A mailbox lets it watch what arrives; an MCP server gives it tools.
conn-open-catalogue = Open the catalogue
conn-calls-today = { $count ->
    [0] no call today
    [one] 1 call today
   *[other] { $count } calls today
}
conn-no-connector = No connector is installed on this instance.
conn-feeds-watches = feeds watches
conn-accounts-count = { $count ->
    [one] 1 account
   *[other] { $count } accounts
}
conn-client-to-create = client to create
conn-connect-ellipsis = Connect…

conn-connect = Connect
conn-connecting = Connecting…
conn-redirecting = Redirecting to the service…
conn-connected = Connected
conn-connect-account = Connect an account
conn-oauth-consent = You will give your consent on the service's page, then come back here.
conn-account-of = Account of
conn-account-of-hint = Its tools will serve this person, or the whole household.
conn-field-optional = { $label } (optional)
conn-client-first = Register the household's OAuth client first.
conn-status-redirecting = [ on the way to the provider ]
conn-status-pending = [ in progress ]
conn-reconnect-note = Reconnecting: the old access stays active until the new one works, and its settings are kept.

conn-client-title = Household OAuth client
conn-client-registered = registered
conn-client-missing = to create
conn-client-id = Client ID
conn-client-why = Each household declares its own application with the provider: no secret is shared between instances.
conn-redirect-uri = Redirect URI to declare with the provider
conn-redirect-uri-label = the redirect URI
conn-relayed = Without HTTPS, the provider sends your browser to this public relay page, which forwards it here at once. The authorisation code passes through it but is useless without the key this instance keeps.
conn-client-replace-ellipsis = Replace the client…
conn-client-register-ellipsis = Register the client…
conn-client-replace-title = Replace the OAuth client
conn-client-register-title = Register the OAuth client
conn-client-replace-note = Only if it changed at the provider: connected accounts keep working.
conn-client-saved = OAuth client registered: you can connect an account.
conn-client-id-field = Client ID
conn-client-secret-field = Client secret
conn-client-register = Register the client

conn-tools = Tools
conn-tools-saved = Tool settings saved.
conn-no-tools = This service brings no tool.
conn-confirm-writes = Ask for confirmation before writing
conn-confirm-writes-hint = Sensitive actions, such as sending, always ask.
conn-unsaved = ● unsaved changes

conn-sections = Connection sections
conn-tab-overview = Overview
conn-tab-activity = Activity
conn-tab-settings = Settings
conn-owner = account of { $name }
conn-connected-at = connected { $when }
conn-broken = { $assistant } can no longer use this account: its tools are hidden and its watches are waiting.
conn-reconnect = Reconnect
conn-reconnect-ellipsis = Reconnect…
conn-reconnect-hint = To change account or password: the new access replaces the old one and keeps its tool settings.
conn-summary-owned = The { $service } account of { $name }.
conn-summary-household = A { $service } service for the whole household.
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
        [yes] , always after confirmation.
       *[no] {" "}without confirmation.
    }
   *[other] , { $writes } of which write{ $confirm ->
        [yes] , always after confirmation.
       *[no] {" "}without confirmation.
    }
}
conn-latest-uses = Latest uses
conn-never-used = { $assistant } has not used it yet.
conn-no-activity = No event involves this connection yet.
conn-disconnected = Account { $account } disconnected: its access was revoked and forgotten.
conn-read-only = Your role does not allow changing this connection.
conn-disconnect = Disconnect
conn-disconnect-ellipsis = Disconnect…
conn-disconnect-hint = Access is revoked at the provider when possible, then every secret of this account is forgotten.
conn-disconnect-title = Disconnect { $account }?
conn-disconnect-consequence = Its tools disappear at once and the watches that depend on it stop. To get it back, you will have to connect it again.
conn-account-connected = Account { $account } connected.

conn-failed-crumb = Failure
conn-failed-denied = Authorisation refused
conn-failed-denied-text = Access was refused on the service's page: nothing was connected.
conn-failed-expired = Authorisation request expired
conn-failed-expired-text = More than ten minutes passed between leaving and coming back: start again.
conn-failed-unknown = Unknown authorisation request
conn-failed-unknown-text = This return matches no connection started from this session. Start again from the catalogue.
conn-failed-exchange = Exchange refused by the service
conn-failed-exchange-text = The service did not accept the authorisation code. Check the OAuth client, then start again.
conn-failed-other = The service returned an error
conn-failed-other-text = Error reported by the service: “{ $error }”.
conn-failed-no-code = no code
conn-failed-retry = Start again
conn-failed-back = Back to connections
