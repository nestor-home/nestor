## The frame around every screen: navigation, status line, account menu, command palette.

nav-journal = Journal
nav-people = People
nav-memories = Memories
nav-connections = Connections
nav-satellites = Satellites
nav-system = System
nav-accounts = Accounts
nav-config = Configuration

shell-skip = Skip to content
shell-home-link = { $assistant } · Nestor
shell-sections = Sections
shell-account-menu = Account menu
shell-theme = Theme
shell-theme-system = System
shell-theme-light = Light
shell-theme-dark = Dark
shell-language = Language
shell-sign-out = Sign out
shell-display = Display
shell-theme-to-light = Switch to light
shell-theme-to-dark = Switch to dark

shell-live-connecting = connecting…
shell-version = nestor { $version }
shell-go-to = Go to…
shell-palette-description = Find a section, a person, a service
shell-palette-placeholder = Section, person, connection…
shell-palette-empty = No results.
shell-palette-theme-keywords = theme light dark

attention-reauth = { $account } needs reauthorising
attention-connection-error = { $account } no longer answers
attention-tools-hidden = Its tools are paused.
attention-reconnect = Reconnect
attention-confirmation = { $tool } waits for your go-ahead
attention-confirmation-detail = Asked aloud; dropped at { $at } without an answer.
attention-answer = Answer
attention-home = { $health ->
    [unavailable] The home system does not answer
   *[other] The home system answers in part
}
attention-pairing = { $device } is waiting to be paired
attention-pairing-detail = { $model }, { $room }: type the code it shows.
attention-approve = Approve
attention-satellite-offline = { $device } is offline
attention-satellite-offline-detail = It no longer listens or speaks in the { $room }.
attention-understand = Details
attention-task-failed = The task “{ $objective }” failed
attention-component-down = { $name } is down
shell-agent-offline = offline
shell-agent-label = { $assistant }, { $state }

## The spaces of the rail
space-today = Today
space-chat = Talk
space-activity = Ongoing
space-house = The house
space-settings = Settings

## Settings
set-lede = What { $assistant } is made of: the services it uses, the devices in the rooms, who may do what.
set-connections = The accounts and services it uses: mail, calendar, tools.
set-connections-count = { $count ->
    [0] No connection
    [one] One connection
   *[other] { $count } connections
}
set-satellites = The devices it hears, speaks and sees through in each room.
set-satellites-count = { $count ->
    [0] No device
    [one] One device
   *[other] { $count } devices
}
set-satellites-offline = { $count } devices, { $offline } offline
set-accounts = Who may open this interface, and with which rights.
set-accounts-count = { $count ->
    [one] One account
   *[other] { $count } accounts
}
set-config = Models, voices, channels, home: everything that tunes { $assistant }.
set-system = The state of every component, updates, restart.
