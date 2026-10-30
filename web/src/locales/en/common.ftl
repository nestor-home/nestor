## Shared by every screen: time, counts, roles, statuses, generic actions and errors.

time-today = today { $time }
time-yesterday = yesterday { $time }
time-day = { $day } { $time }
time-just-now = just now
day-today = today
day-yesterday = yesterday
remaining = { $minutes } min { $seconds } s
duration-ms = { $ms } ms
duration-s = { $seconds } s
duration-min = { $minutes } min { $seconds }
duration-h = { $hours } h { $minutes }

household-everyone = whole household
household-nobody = nobody

role-owner = owner
role-admin = administrator
role-member = member
role-owner-hint = Everything, accounts and roles included.
role-admin-hint = Connections, satellites and supervision; not accounts.
role-member-hint = Their own journal, connections and memories.

connection-status-connected = connected
connection-status-needs-reauth = needs reauthorisation
connection-status-error = error
risk-read = read
risk-write = write
risk-sensitive = sensitive
auth-oauth2 = OAuth
auth-secret = credentials
auth-none = none
task-status-running = running
task-status-completed = completed
task-status-failed = failed
task-status-cancelled = cancelled

action-cancel = Cancel
action-save = Save
action-saving = Saving…
action-retry = Try again
action-close = Close
action-copy = copy
action-copied = copied
action-copy-label = Copy { $what }
action-choose = Choose…
action-see = See
loading = Loading…
empty-generic = Nothing here yet.

error-network = Nestor does not answer. Check that it is running, then try again.
error-unauthenticated = Your session has expired: sign in again.
error-forbidden = Your role does not allow this.
error-not-found = Not found: this no longer exists.
error-status = Nestor answered with an error ({ $status }).
error-unexpected = Something unexpected happened.

forbidden-title = Restricted section
forbidden-text = Your role does not give access to this part of the admin. The household's owner can change your role from Accounts.
not-found-title = This page does not exist
not-found-text = The address may be old or mistyped.
not-found-back = Back to today
household-everyone-capital = Whole household
breadcrumbs = Breadcrumbs
person-picker-empty = Nobody by that name.
action-show-choices = Show the choices
role-guest = guest
role-guest-hint = Their own journal only.
