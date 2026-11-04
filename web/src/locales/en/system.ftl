## System: what this instance assembled at start-up, and the health of each part.

sys-title = System
sys-started = started
sys-unwell = { $count ->
    [one] 1 component to watch
   *[other] { $count } components to watch
}
sys-all-well = all is well
sys-slot-model = Models
sys-slot-speech = Speech
sys-slot-executor = Executors
sys-slot-channel = Channels
sys-slot-presence = Presence
sys-slot-tools = Tools
sys-slot-connector = Connectors
sys-slot-satellite = Satellites
sys-slot-storage = Storage and runtime
sys-health-ok = ok
sys-health-degraded = degraded
sys-health-down = down
sys-health-unknown = unknown

## Updates: a newer Nestor, what changed and how to install it.

upd-available = New release
upd-available-version = Update available: { $version }
upd-title = Nestor { $version } is here
upd-description = What changed since your version, and how to update.
upd-behind = { $count ->
    [one] one release behind
   *[other] { $count } releases behind
}
upd-install = Install { $version }
upd-install-title = Install Nestor { $version }?
upd-install-description = Nestor installs the new release, checks it accepts your configuration, then restarts. Conversations pause for a moment. If anything goes wrong, it stays on { $running }.
upd-install-confirm = Install and restart
upd-install-hint = It restarts once installed.
upd-installing = Installing { $version }…
upd-failed = { $version } did not install. Nestor stays on { $running }.
upd-breaking = This release changes the data or the configuration: read the notes before updating.
upd-outdated = { $count ->
    [one] This satellite will no longer connect: update it first.
   *[other] These { $count } satellites will no longer connect: update them first.
}
upd-release = Release { $version }
upd-notes = Release notes
upd-kind-breaking = Breaking changes
upd-kind-feature = Features
upd-kind-fix = Fixes
upd-kind-other = Other
upd-how = Update
upd-how-container = Nestor runs in a container: pull the new image, then start it again, in the folder of compose.yaml.
upd-how-uv-tool = On Nestor's machine, update the tool:
upd-how-pip = On Nestor's machine, update the package:
upd-how-editable = Nestor runs from a development checkout: update it with git.
upd-then-restart = Then restart Nestor to run the new version.
upd-then-ask = Then ask an administrator to restart Nestor.
upd-command = the command
