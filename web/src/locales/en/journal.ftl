## The journal: stories (conversations, chains, lone events), lanes, filters, live edge, event sheet.

jr-title = Journal
jr-loading = Loading the journal…
jr-empty = No events for these filters.
jr-empty-hint = Widen the time range or drop a filter.
jr-older = Older
jr-beginning = Beginning of the journal
jr-now = Live
jr-paused = Paused
jr-new-events = { $count ->
    [one] 1 new event
   *[other] { $count } new events
}
jr-event-count = { $count ->
    [one] 1 event
   *[other] { NUMBER($count) } events
}
jr-day-list = Journal of { $day }

jr-search-label = Search the journal
jr-search-placeholder = Parcel, invoice, Jules…
jr-search-clear = Clear the search
jr-range-hour = Last hour
jr-range-today = Today
jr-range-day = Last 24 hours
jr-range-week = Last 7 days
jr-range-all = All time
jr-range-since = Since { $from }
jr-range-until = Until { $to }
jr-range-between = { $from } → { $to }
jr-pause = Pause
jr-resume = Resume
jr-pause-hint = Pause the live journal (p)

jr-facet-kind = Kind
jr-facet-person = Person
jr-facet-channel = Channel
jr-facet-room = Room
jr-facet-clear = Clear filters
jr-facet-search = Filter { $facet }…
jr-facet-empty = No results.
jr-facet-selected = { $count } selected

jr-histogram-label = { $count ->
    [one] 1 event
   *[other] { $count } events
} between { $from } and { $to }

jr-story-thread = Conversation
jr-story-chain = Sequence
jr-story-single = Event
jr-thread-open = Open the conversation
jr-thread-link = Whole thread
jr-thread-earlier = … the conversation started earlier
jr-entry-label = { $text }: { $detail }
jr-file-count = { $count ->
    [one] 1 file
   *[other] { $count } files
}
jr-tool-count = { $count ->
    [one] 1 tool
   *[other] { $count } tools
}
jr-turn-count = { $count ->
    [one] 1 turn
   *[other] { $count } turns
}
jr-more-turns = { $count ->
    [one] Show the other turn
   *[other] Show the { $count } other turns
}
jr-cut-by = Interrupted by: “{ $heard }”
jr-attachment-image = Photo
jr-attachment-voice = Voice message
jr-attachment-audio = Audio file
jr-attachment-file = File
jr-attachment-unheard = could not be transcribed
jr-between-details = What happened: { $what }
jr-details = details
jr-fallback = fallback answer
jr-memory-kept = memory saved
jr-call-details = Tool { $tool }: details
jr-call-running = running
jr-call-ok = ok
jr-call-failed = failed
jr-call-arguments = arguments
jr-call-result = result
jr-chain-task = Task · { $what }
jr-chain-task-link = task
jr-chain-alert = Alert · { $what }
jr-chain-alert-link = alert
jr-chain-delivery = Speaking up
jr-channel-voice = voice
jr-why-label = why:

step-task-started = opened
step-task-instructed = instruction
step-task-steered = reoriented
step-task-progressed = step
step-task-delivered = passed on
step-task-stopped = stopped
step-task-completed = came back
step-task-asked = question
step-task-failed = failed
step-task-reminded = reminder
step-alert-created = created
step-alert-rang = rang
step-considered = decision
step-follow-up = follow-up
step-delivered-spoken = said out loud
step-delivered-written = written
step-withheld = nothing to tell
step-delivery-failed = not delivered

jr-event = Event
jr-related-person = Person
jr-related-conversation = Conversation
jr-related-session = Session
jr-related-task = Task
jr-related-alert = Alert
jr-related-connection = Connection
jr-related-satellite = Satellite
jr-related-memory = Memory
jr-related-cause = Caused by
jr-raw = Raw record
jr-raw-copy = the raw record
jr-all-in-journal = See in the journal
jr-subject-conversation = Conversation
jr-subject-session = Session
jr-subject-task = Task
jr-subject-alert = Alert
jr-subject-connection = Connection
jr-subject-satellite = Satellite
jr-subject-tone = Tone
jr-subject-remove = Remove the filter { $subject } { $id }
jr-filters = Filters
jr-filters-show = Show
jr-chip-remove = Remove the filter { $value }
jr-range-label = Time range
jr-offline = Live stream cut
jr-lanes = Kind of story
jr-lane-all = All
jr-lane-talk = Conversations
jr-lane-own = On its own
jr-lane-tasks = Tasks
jr-lane-alerts = Alerts
jr-lane-memory = Memory
jr-lane-problems = Problems
jr-fact-room = Room
jr-fact-channel = Channel
jr-fact-through = Through
jr-fact-took = Took
