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
upd-description = What changed since your version.
upd-behind = { $count ->
    [one] one release behind
   *[other] { $count } releases behind
}
upd-breaking = This release changes the data or the configuration: read the notes before updating.
upd-by-hand = Update Nestor the way you installed it, then restart it.
upd-release = Release { $version }
upd-notes = Release notes
upd-kind-breaking = Breaking changes
upd-kind-feature = Features
upd-kind-fix = Fixes
upd-kind-other = Other
