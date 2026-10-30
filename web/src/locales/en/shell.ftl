## The frame around every screen: navigation, status line, account menu, command palette.

nav-today = Today
nav-journal = Journal
nav-group-household = Household
nav-people = People
nav-memories = Memories
nav-watches = Watches
nav-tasks = Tasks
nav-group-installation = Setup
nav-connections = Connections
nav-satellites = Satellites
nav-system = System
nav-accounts = Accounts

shell-skip = Skip to content
shell-home-link = Nestor — { $assistant }
shell-sections = Sections
shell-account-menu = Account menu
shell-theme = Theme
shell-theme-system = Like the system
shell-theme-light = Light
shell-theme-dark = Dark
shell-language = Language
shell-sign-out = Sign out
shell-display = Display
shell-theme-to-light = Switch to light
shell-theme-to-dark = Switch to dark

shell-live-open = live
shell-live-connecting = connecting…
shell-live-closed = offline
shell-live-hint = The journal arrives live from Nestor
shell-ticker-tasks = { $count ->
    [one] 1 task running
   *[other] { $count } tasks running
}
shell-ticker-watches = { $count ->
    [one] 1 watch
   *[other] { $count } watches
}
shell-ticker-satellites = { $online }/{ $total } satellites
shell-ticker-attention = { $count ->
    [one] 1 thing to look at
   *[other] { $count } things to look at
}
shell-version = nestor { $version }
shell-go-to = Go to…
shell-palette-description = Find a section, a person, a service
shell-palette-placeholder = Go to… (section, person, connection)
shell-palette-empty = Nothing by that name.
shell-palette-theme-keywords = theme light dark

attention-reauth = { $account } needs reauthorising
attention-connection-error = { $account } no longer answers
attention-tools-hidden = Its tools are hidden until then.
attention-reconnect = Reconnect
attention-pairing = { $device } is waiting to be paired
attention-pairing-detail = { $model }, { $room }: type the code it shows.
attention-approve = Approve
attention-satellite-offline = { $device } is offline
attention-satellite-offline-detail = Nobody can be heard or told anything out loud in the { $room }.
attention-understand = Understand
attention-task-failed = The task “{ $objective }” failed
attention-component-down = { $name } is down
shell-sidebar-toggle = Toggle the sidebar
shell-sidebar-collapse = Collapse
shell-sidebar-expand = Expand
shell-open-menu = Open the menu
shell-agent-online = online
shell-agent-offline = offline
shell-agent-label = { $assistant }, { $state }
