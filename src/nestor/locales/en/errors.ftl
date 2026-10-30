# Errors of the admin API (`error-<code>`): shown as is to the person.

error-unauthenticated = Sign in to continue.
error-bad-token = The admin token is missing or wrong.
error-forbidden = Your account cannot use this.
error-csrf-failed = Request refused: reload the page and try again.
error-unsupported-media-type = The request body must be JSON.
error-not-found = This does not exist (or no longer).
error-method-not-allowed = Method not allowed.
error-http-error = Request refused.
error-invalid-request = Invalid request ({ $fields }).
error-invalid = Not possible: { $detail }.
error-provider-error = The service could not answer: { $detail }.
error-invalid-credentials = Wrong login or password.
error-throttled = Too many attempts. Try again in { $minutes ->
    [one] one minute
   *[other] { $minutes } minutes
}.
error-weak-password = Choose a password of at least { $length } characters.
error-invalid-login = A login is an email or a username (letters, digits, . _ + @ -).
error-wrong-password = The current password is wrong.
error-use-me-password = For your own password, go through your profile.
error-unknown-locale = This language is not available.
error-last-owner = The household must keep at least one owner: make someone else owner first.
error-conflict = This login is taken, or this person already has an account.
error-unknown-person = Choose a person of the household.
error-person-required = A member or guest account belongs to a person of the household.
error-invitation-unknown = This invitation is unknown.
error-invitation-used = This invitation has already been used.
error-invitation-expired = This invitation has expired: ask for a new one.
error-invitation-revoked = This invitation was withdrawn.
error-no-connectors = No connector is installed on this instance.
error-connector-unknown = No connector “{ $kind }” is installed.
error-connection-unknown = This connection does not exist or was removed.
error-not-oauth = { $connector } does not connect through OAuth.
error-oauth = { $connector } connects through OAuth.
error-client-incomplete = Give the OAuth client's id and secret.
error-client-missing = Register this service's OAuth client first.
error-own-connections-only = You can only connect an account for yourself.
error-fields-missing = Missing fields: { $fields }.
error-provider-refused = The service refused the connection: { $detail }.
error-unknown-tool = Unknown tools: { $tools }.
error-invalid-code = The code is 6 digits, read on the device.
error-pairing-refused = No device is waiting with this code: it is wrong or has expired.
error-satellite-unknown = This satellite is not (or no longer) paired.
error-unknown-kind = Unknown kind: { $kind }.
error-task-unknown = This task does not exist or has already ended.
error-watch-unknown = This watch does not exist or has already ended.
error-memory-unknown = This memory does not exist (or no longer).
error-memory-shared = Only the household's administration changes shared memories.
error-empty-memory = To erase a memory, forget it.
error-journal-entry-unknown = This journal entry does not exist, or is not yours to read.
error-cross-origin = Request refused: it does not come from this admin.
error-person-unknown = This person is not part of the household.
error-config-unavailable = This instance was not started from a configuration file: there is nothing to edit.
error-no-secret-key = NESTOR_SECRET_KEY is not set: secrets cannot be kept without it.
error-config-invalid = The configuration cannot be used ({ $count ->
    [one] one problem
   *[other] { $count } problems
}): nothing was written.
error-config-history-unknown = This earlier configuration does not exist.
error-secret-in-use = This secret is still used by { $paths }: remove those references first.
error-secret-unknown = This secret is not set.
error-restart-unconfirmed = Confirm the restart: every conversation will be interrupted for a moment.
