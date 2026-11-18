## Connections: connected accounts, the catalogue, connecting a service, one connection's pages.

conn-title = Connections
conn-intro = Tokens are encrypted and never shown to the model. Only enabled tools are used.
conn-connect-service = Connect a service

conn-empty = No account connected yet.
conn-empty-hint = A mailbox for watches, an MCP server for tools.
conn-open-catalogue = Open the catalogue
conn-no-connector = No connector installed.
conn-feeds-watches = feeds watches
conn-accounts-count = { $count ->
    [one] 1 account
   *[other] { $count } accounts
}
conn-client-to-create = OAuth client missing

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
conn-unsaved = Unsaved changes.

conn-sections = Connection sections
conn-tab-overview = Overview
conn-tab-activity = Activity
conn-tab-settings = Settings
conn-connected-at = connected { $when }
conn-broken = { $assistant } can no longer use this account: its tools and watches are paused.
conn-reconnect = Reconnect
conn-reconnect-ellipsis = Reconnect…
conn-reconnect-hint = To switch account or password. Tool settings are kept.
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

conn-services = In a message
conn-services-hint = Write the handle in a chat to point { $assistant } at this account.
conn-service-unnamed = once reconnected
conn-failed-crumb = Failure
conn-failed-denied = Authorisation refused
conn-failed-denied-text = Nothing was connected.
conn-failed-expired = Authorisation request expired
conn-failed-expired-text = More than ten minutes passed.
conn-failed-unknown = Unknown authorisation request
conn-failed-unknown-text = It was not started from this session.
conn-failed-exchange = Code refused by the service
conn-failed-exchange-text = The service did not accept the code with the OAuth client registered here.
conn-failed-forbidden = Connection no longer allowed
conn-failed-forbidden-text = The account that started it can no longer connect this service.
conn-failed-provider = The service did not authorise it
conn-failed-other = The service returned an error
conn-failed-other-text = Error: “{ $error }”.
conn-failed-no-code = no code
conn-failed-retry = Start again
conn-failed-back = Back to connections

conn-lanes = Accounts shown
conn-lane-all = All
conn-lane-attention = To reconnect
conn-attention-title = To reconnect
conn-attention-empty = I can use every account.
conn-working-title = Connected
conn-fix-reauth = The service no longer accepts the access it gave. Reconnect the account: its settings are kept.
conn-fix-error = The service did not answer as expected. Check the reason given, then reconnect the account if it lasts.
conn-last-used = last used
conn-never-used-short = never used

conn-catalogue = Catalogue
conn-catalogue-lede = An account belongs to one person or to the whole household: you choose when you connect it.
conn-catalogue-read-only = Your role does not allow connecting a service.
conn-group-accounts = Mail, calendars and files
conn-group-tools = Tool servers
conn-other-server = Another server

conn-glance = At a glance
conn-figure-calls = Calls today
conn-figure-tools = Tools on
conn-figure-writes = { $count ->
    [0] none can write
    [one] 1 can write
   *[other] { $count } can write
}
conn-figure-confirm = Asks before writing
conn-yes = Yes
conn-no = No
conn-figure-watches = Watches fed
conn-figure-watches-note = { $count ->
    [0] none depends on this account
   *[other] they stop if you disconnect
}
conn-who = Who may use it
conn-who-owner = { $assistant } uses it only for { $name }.
conn-who-household = { $assistant } uses it for anyone in the household.

conn-failed-next = Next step
conn-failed-denied-next = Start again and accept the access on the service's page.
conn-failed-expired-next = Start again and finish on the service's page without waiting.
conn-failed-unknown-next = Start again from the catalogue.
conn-failed-exchange-next = Check the OAuth client, then start again.
conn-failed-forbidden-next = Sign in with an account that can, then start again.
conn-failed-provider-next = Start again. If it happens again, check the OAuth client in the service's console.
conn-failed-other-next = Start again. If it happens again, look this error up in the service's documentation.
