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
