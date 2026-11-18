## Home: the home system (Home Assistant), as Nestor sees it.

house-lede = It tells { $granularity }. Lights, heating and media need no confirmation; what you mark sensitive does.
house-configure = Configure
house-none = No home system plugged in.
house-none-hint = Connect Home Assistant: presence, rooms and actions in one place.
house-people = People it follows
house-not-tied = not tied: presence unknown
house-actions = Actions
house-actions-empty = No action available.
house-actions-empty-hint = The home system's MCP server does not answer, or exposes nothing to Assist.
house-action-confirmed-when = confirmed depending on its target
house-unplaced = { $count ->
    [one] 1 occupancy sensor has no room: it is ignored.
   *[other] { $count } occupancy sensors have no room: they are ignored.
}
house-strangers = { $count ->
    [one] It also knows { $names }, tied to nobody of the household.
   *[other] It also knows { $names }, tied to nobody of the household.
}

## The "house" space
hs-lede = Who lives here, where each one is, and what { $assistant } hears, speaks and sees through in each room.
hs-system = Home system
hs-people = The household
hs-rooms = The rooms
hs-rooms-empty = No room known yet: add a satellite or plug a home system.
hs-media = Watch and call
hs-room-events = { $count ->
    [one] once today
   *[other] { $count } times today
}
hs-memories = { $count ->
    [one] One memory kept by { $assistant }
   *[other] { $count } memories kept by { $assistant }
}
hs-media-off = Watching and calling are off on this server.
hs-media-off-hint = Install Nestor with the “media” extra to relay the devices' picture and sound.
hs-add-person = Add a person
