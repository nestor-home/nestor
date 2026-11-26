## System: what this instance assembled at start-up, and the health of each part.

sys-title = System
sys-unwell = { $count ->
    [one] 1 component to watch
   *[other] { $count } components to watch
}
sys-all-well = all is well
sys-slot-model = Models
sys-slot-executor = Executors
sys-slot-channel = Channels
sys-slot-home = Home
sys-slot-tools = Tools
sys-slot-inbound = Inbound sources
sys-slot-connector = Connectors
sys-slot-satellite = Satellites
sys-health-ok = ok
sys-health-degraded = degraded
sys-health-down = down
sys-health-unknown = unknown

## Updates: a newer Nestor, what changed and how to install it.

upd-available = New release
upd-available-version = Update available: { $version }
upd-title = Nestor { $version } is here
upd-description = Release notes and how to update.
upd-behind = { $count ->
    [one] one release behind
   *[other] { $count } releases behind
}
upd-install = Install { $version }
upd-install-title = Install Nestor { $version }?
upd-install-description = Nestor installs the new release, checks your configuration, then restarts. If it fails, it stays on { $running }.
upd-install-confirm = Install and restart
upd-install-hint = Restarts after installing.
upd-installing = Installing { $version }…
upd-failed = { $version } did not install. Nestor stays on { $running }.
upd-breaking = This release changes the data or the configuration: read the notes before updating.
upd-outdated = { $count ->
    [one] This satellite will no longer connect: update it on the device, after the server.
   *[other] These { $count } satellites will no longer connect: update them on each device, after the server.
}
upd-release = Release { $version }
upd-notes = Release notes
upd-kind-breaking = Breaking changes
upd-kind-feature = Features
upd-kind-fix = Fixes
upd-kind-other = Other
upd-how = Update
upd-how-container = In the folder of compose.yaml:
upd-how-uv-tool = On Nestor's machine:
upd-how-pip = On Nestor's machine:
upd-how-editable = Nestor runs from a checkout: update it with git.
upd-then-restart = Then restart Nestor.
upd-then-ask = Then ask an administrator to restart Nestor.
upd-command = the command
sys-fallback = fallback: { $model }

sys-executors = Nestor's tools for executors
sys-executors-intro = While they work on a task, executors reach Nestor at { $url }: their brief, what the requester said before, questions to them, their files. Each one calls with its own key.
sys-executors-off = Executors cannot reach Nestor: give the admin a public_url and set NESTOR_SECRET_KEY, then restart.
sys-executor-tools = { $tools ->
    [passed] Nestor hands it its tools with each task
    [configured] Its own configuration declares Nestor's tools
   *[none] Works without Nestor's tools
}
sys-executor-key-made = Key made
sys-executor-key-used = last used
sys-executor-key-unused = not used yet
sys-executor-no-key = No key
sys-executor-key-make = Make a key
sys-executor-key-renew = Renew
sys-executor-key-revoke = Revoke
sys-executor-make-title = Make a key for { $name }?
sys-executor-make-body = { $tools ->
    [passed] Nestor hands it to { $name } with each task.
   *[other] It is shown once, to paste in the configuration of { $name }.
}
sys-executor-renew-title = Renew the key of { $name }?
sys-executor-renew-body = The current key stops working at once. { $tools ->
    [passed] Nestor hands the new one to { $name } with its next task.
   *[other] Paste the new one in the configuration of { $name }.
}
sys-executor-revoke-title = Revoke the key of { $name }?
sys-executor-revoke-body = { $name } no longer reaches Nestor's tools, nor do the tasks it is working on.
sys-executor-key-title = The key of { $name }
sys-executor-key-once = Shown only now: Nestor keeps it encrypted and never shows it again.
sys-executor-key-label = the key
sys-executor-passed = Nestor hands it to { $name } with each task: nothing to paste.
sys-executor-profile = Add this to the configuration of { $name } (a Hermes profile's config.yaml), then set nestor_mcp: true on this executor in Nestor's configuration.
sys-executor-setup-label = what to add
sys-parts = { $count ->
    [one] 1 component
   *[other] { $count } components
}
sys-attention = To look at
sys-instance = This instance
sys-slot-voice = Voice
sys-fix-down = Nothing goes through it for now. Check that the service behind it answers and that its settings are right.
sys-fix-degraded = It works in part: what it reports says what is missing.
sys-configure = Configure
sys-docs = Documentation
sys-fact-state = state
sys-fact-service = service
sys-fact-type = type
sys-fact-fallback = fallback
sys-fact-adapter = adapter
sys-fact-version = version
sys-fact-can = can
sys-runs = Runs { $agent }.
sys-restart-waiting = { $count ->
    [0] A restart is waiting.
    [one] 1 change waits for a restart.
   *[other] { $count } changes wait for a restart.
}
sys-restart = Restart…
sys-restart-title = Restart { $agent }?
sys-restart-text = It stops cleanly and starts again in a few seconds. A conversation under way is cut, delegated tasks keep running, and everyone signs in again.
sys-restart-now = Restart now
upd-available-running = { $latest } is out. This instance runs { $running }.
