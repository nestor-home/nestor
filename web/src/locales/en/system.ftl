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
upd-title = Nestor { $version } is out
upd-running = { $count ->
    [one] You run { $version }. Here is what changed since.
   *[other] You run { $version }, { $count } releases behind. Here is what changed since.
}
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
upd-how-package = On Nestor's machine, update the package:
upd-how-pip = Or, if it was installed with pip:
upd-then-restart = Then restart Nestor to run the new version.
upd-then-ask = Then ask an administrator to restart Nestor.
upd-command = the command
