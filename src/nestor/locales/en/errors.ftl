# Errors of the admin API (`error-<code>`): shown as is to the person.

error-unauthenticated = Sign in to continue.
error-bad-token = Admin token missing or invalid.
error-forbidden = Your account cannot use this.
error-csrf-failed = Request refused: reload the page and try again.
error-unsupported-media-type = The request body must be JSON.
error-not-found = Not found.
error-method-not-allowed = Method not allowed.
error-http-error = Request refused.
error-invalid-request = Invalid request ({ $fields }).
error-invalid = Not possible: { $detail }.
error-provider-error = The service is not responding: { $detail }.
error-invalid-credentials = Wrong login or password.
error-throttled = Too many attempts. Try again in { $minutes ->
    [one] one minute
   *[other] { $minutes } minutes
}.
error-weak-password = Choose a password of at least { $length } characters.
error-invalid-login = A login is an email or a username (letters, digits, . _ + @ -).
error-wrong-password = The current password is wrong.
error-use-me-password = Change your own password from your profile.
error-unknown-locale = This language is not available.
error-last-owner = The household must keep at least one owner: make someone else owner first.
error-conflict = This login is taken, or this person already has an account.
error-unknown-person = Choose a person of the household.
error-person-required = A member or guest account must be linked to a person of the household.
error-invitation-unknown = Invitation not found.
error-invitation-used = This invitation has already been used.
error-invitation-expired = This invitation has expired: ask for a new one.
error-invitation-revoked = This invitation was withdrawn.
error-no-connectors = No connector is installed on this instance.
error-connector-unknown = No connector “{ $kind }” is installed.
error-connection-unknown = This connection does not exist or was removed.
error-not-oauth = { $connector } does not connect through OAuth.
error-oauth = { $connector } connects through OAuth.
error-client-incomplete = Fill in the OAuth client ID and secret.
error-client-missing = Register this service's OAuth client first.
error-own-connections-only = You can only connect an account for yourself.
error-fields-missing = Missing fields: { $fields }.
error-provider-refused = The service refused the connection: { $detail }.
error-unknown-tool = Unknown tools: { $tools }.
error-invalid-code = The code is 6 digits, shown or said by the device.
error-pairing-refused = No device is waiting with this code: it is wrong, has expired, or the device is already paired.
error-not-a-device-code-method = This method does not pair with a code typed here.
error-addition-unknown = Addition not found.
error-addition-over = This addition is over: device paired, addition cancelled or expired.
error-too-many-additions = Too many additions are in progress. Cancel one first.
error-pending-unknown = This device is no longer waiting to pair.
error-identify-unsupported = This device does not support identify.
error-satellite-offline = This satellite is not connected right now.
error-update-unsupported = This device does not support updates.
error-update-unavailable = This satellite found no new version.
error-satellite-unknown = This satellite is not paired.
error-task-unknown = This task does not exist or has already ended.
error-watch-unknown = This watch does not exist or has already ended.
error-memory-unknown = Memory not found.
error-memory-shared = Only administrators change shared memories.
error-empty-memory = A memory cannot be empty. To erase it, forget it.
error-journal-entry-unknown = Journal entry not found.
error-cross-origin = Request refused: it does not come from this admin.
error-person-unknown = This person is not part of the household.
error-config-unavailable = Nestor was not started with a configuration file: nothing to edit.
error-no-secret-key = NESTOR_SECRET_KEY is not set: secrets cannot be stored.
error-config-invalid = The configuration cannot be used ({ $count ->
    [one] one problem
   *[other] { $count } problems
}): nothing was written.
error-config-history-unknown = Configuration version not found.
error-secret-in-use = This secret is still used by { $paths }: remove those references first.
error-secret-unknown = This secret is not set.
error-restart-unconfirmed = Confirm the restart: ongoing conversations will be cut for a moment.
error-update-unconfirmed = Confirm the update: Nestor restarts once it is installed.
error-update-not-installable = This release cannot be installed from here.

error-voices-off = Voice recognition is off: choose a model under voices in the configuration.
error-voice-not-yours = Everyone records their own voice. An owner can do it for someone without an account.
error-audio-format = The recording must be a 16-bit mono WAV at 16 kHz.
