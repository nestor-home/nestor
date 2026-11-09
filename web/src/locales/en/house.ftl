## Home: the home system (Home Assistant), as Nestor sees it.

house-title = Home
house-lede = It tells { $granularity }. Lights, heating and media need no confirmation; what you mark sensitive does.
house-configure = Configure
house-none = No home system plugged in.
house-none-hint = Connect Home Assistant: presence, rooms and actions in one place.
house-people = Who is where
house-not-tied = not tied: presence unknown
house-rooms = Rooms
house-rooms-empty = No room in the home system.
house-room-occupied = occupied
house-room-empty = empty
house-room-people = people
house-room-satellites = satellites
house-room-nobody = nobody known
house-residents = Known to the home system
house-resident-tied = tied to { $name }
house-resident-untied = tied to nobody
house-actions = Actions
house-actions-empty = No action available.
house-actions-empty-hint = The home system's MCP server does not answer, or exposes nothing to Assist.
house-action-confirmed-when = confirmed for locks, alarm, doors
house-unplaced = { $count ->
    [one] 1 occupancy sensor has no room: it is ignored.
   *[other] { $count } occupancy sensors have no room: they are ignored.
}
