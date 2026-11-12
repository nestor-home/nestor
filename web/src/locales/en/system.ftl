## System: what this instance assembled at start-up, and the health of each part.

sys-title = System
sys-started = started
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
