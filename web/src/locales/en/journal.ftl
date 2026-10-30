## The journal: stories (conversations, chains, lone events), filters, live edge, event drawer.

jr-title = Journal
jr-intro = Every conversation with its tools, every time it spoke up with its reason, every task until it is handed back.
jr-loading = Loading the journal…
jr-empty = Nothing in the journal for these filters.
jr-empty-hint = Widen the time range or drop a filter; new events appear here as they arrive.
jr-older = Older
jr-beginning = — beginning of the journal —
jr-now = now
jr-paused = paused
jr-new-events = { $count ->
    [one] 1 new event
   *[other] { $count } new events
}
jr-story-count = { $count ->
    [one] 1 story
   *[other] { $count } stories
}
jr-event-count = { $count ->
    [one] 1 event
   *[other] { NUMBER($count) } events
}
jr-day-list = Journal — { $day }

jr-search-label = Search the journal
jr-search-placeholder = Search: parcel, invoice, Jules…
jr-search-clear = Clear the search
jr-range-hour = Last hour
jr-range-today = Today
jr-range-day = Last 24 hours
jr-range-week = Last 7 days
jr-range-all = All time
jr-range-since = Since { $from }
jr-range-until = Until { $to }
jr-range-between = { $from } → { $to }
jr-density = Density
jr-density-comfortable = Comfortable
jr-density-compact = Compact
jr-pause = Pause
jr-resume = Resume
jr-pause-hint = Pause the live journal (p)
jr-keys-browse = browse
jr-keys-search = search
jr-keys-pause = pause

jr-facet-kind = Kind
jr-facet-person = Person
jr-facet-channel = Channel
jr-facet-room = Room
jr-facet-clear = Clear filters
jr-facet-search = Filter { $facet }…
jr-facet-empty = No such value.
jr-facet-selected = { $count } selected

jr-histogram-label = { $count ->
    [one] 1 event
   *[other] { $count } events
} between { $from } and { $to }
jr-histogram-hint = drag to zoom

jr-story-thread = Conversation
jr-story-chain = Chain of events
jr-story-single = Event
jr-thread-title = { $count ->
    [0] Conversation
   *[other] Conversation · { $people }
}
jr-thread-open = Open this conversation alone
jr-thread-link = thread
jr-thread-earlier = … the thread starts on an older page
jr-entry-label = { $text }: { $detail }
jr-tool-count = { $count ->
    [one] 1 tool
   *[other] { $count } tools
}
jr-interrupted = interrupted
jr-call-details = Tool { $tool }: details
jr-call-running = running
jr-call-ok = ok
jr-call-failed = failed
jr-call-arguments = arguments
jr-call-result = result
jr-chain-task = Task · { $what }
jr-chain-task-link = task
jr-chain-watch = Watch · { $what }
jr-chain-watch-link = watch
jr-chain-delivery = Speaking up
jr-channel-voice = voice
jr-why = why

step-task-started = handed over
step-task-progressed = step
step-task-completed = completed
step-task-failed = failed
step-watch-created = created
step-watch-triggered = triggered
step-watch-triaged = triaged
step-considered = decision
step-follow-up = follow-up
step-delivered-spoken = said out loud
step-delivered-written = written
step-delivery-failed = not delivered

jr-event = Event
jr-event-room = { $room }
jr-related = Related to
jr-related-person = Person
jr-related-session = Conversation
jr-related-task = Task
jr-related-watch = Watch
jr-related-connection = Connection
jr-related-satellite = Satellite
jr-related-memory = Memory
jr-related-cause = Caused by
jr-raw = Raw record
jr-raw-copy = the record
jr-all-in-journal = everything in the journal
jr-subject-session = Conversation
jr-subject-task = Task
jr-subject-watch = Watch
jr-subject-connection = Connection
jr-subject-satellite = Satellite
jr-subject-tone = Tone
jr-subject-remove = Remove the filter { $subject } { $id }
jr-filters = Filters
jr-filters-show = Show
jr-chip-remove = Remove the filter { $value }
jr-range-label = Time range
