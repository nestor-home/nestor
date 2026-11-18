## Watches: what the assistant keeps an eye on for the household.

watch-active-empty-hint = Just ask me: “tell me when the parcel arrives”.
watch-for = for { $name }
watch-kind = { $kind ->
    [mail] mail
    [feed] feeds
    [page] web pages
   *[other] { $kind }
}
watch-triggered-count = { $count ->
    [one] 1 trigger
   *[other] { $count } triggers
}
watch-never-triggered = never triggered
watch-unknown = This watch does not exist or was cancelled.
watch-cancelled-notice = All right, I'll stop watching that.
watch-created = created { $when }
watch-until = until { $when }
watch-cancel = Cancel the watch
watch-cancel-action = Cancel the watch…
watch-cancel-title = Cancel this watch?
watch-cancel-description = Nothing more will be reported for “{ $what }”.
watch-found = What it found
watch-found-empty = Nothing relevant yet.
watch-watches = Watches
watch-rhythm = Frequency
watch-rhythm-once = Stops at the first message found.
watch-rhythm-every = Reports every relevant message.
watch-asked-in = Asked in
watch-so-far = So far
watch-last = the last
