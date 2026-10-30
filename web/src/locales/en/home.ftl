## Today: the agent right now — what it perceives, does, intends, did and knows.

home-greeting-night = Good night
home-greeting-day = Hello
home-greeting-evening = Good evening
home-hello = { $greeting }, { $name }.
home-today = today · { $conversations ->
    [0] no conversations
    [one] 1 conversation
   *[other] { $conversations } conversations
} · { $spoken ->
    [0] never spoke up
    [one] spoke up once
   *[other] spoke up { $spoken } times
}

## The map
home-mind-title = What { $agent } perceives right now
home-mind-core = { $agent }, { $state }: see the journal
home-mind-house = the house
home-mind-reach = what it reaches
home-state-listening = listening
home-state-thinking = thinking
home-state-speaking = speaking
home-state-working = working
home-state-idle = idle
home-state-laughing = laughing
home-state-concerned = concerned
home-state-sleeping = resting
home-say-delivered = I just spoke to { $people } · { $where }.
home-say-listening = I'm listening to { $people } · { $where }.
home-say-answering = I'm answering { $people }.
home-say-tool = I'm checking { $tool }.
home-say-presence-room = { $people } is in the { $room }.
home-say-presence-away = { $people } just left.
home-say-memory = Noted, I'll remember that.
home-say-working = { $count ->
    [one] I'm working on “{ $objective }”.
   *[other] I'm working on “{ $objective }” and { $others ->
        [one] one other thing
       *[other] { $others } other things
    }.
}
home-say-concerned = { $count ->
    [one] I need you for one thing.
   *[other] I need you for { $count } things.
}
home-say-sleeping = Quiet hours: I'll keep silent until { $until }.
home-say-idle = All is calm. I'm here if you need me.
home-state-degraded = running degraded
home-room-label = { $room }: { $people }; { $devices ->
    [0] no devices
    [one] 1 device
   *[other] { $devices } devices
}. See what happened there.
home-room-nobody = nobody
home-away = away from home
home-away-label = Away from home: { $names }
home-channels = Channels
home-channels-label = Channels: { $names }
home-task-label = Task: { $objective }, { $steps ->
    [one] 1 step
   *[other] { $steps } steps
}
home-task-steps = { $count ->
    [0] starting
    [one] 1 step
   *[other] { $count } steps
}
home-watches = { $count ->
    [one] 1 watch
   *[other] { $count } watches
}
home-watches-label = { $count ->
    [one] 1 active watch
   *[other] { $count } active watches
}
home-connections = { $count ->
    [one] 1 connection
   *[other] { $count } connections
}
home-connections-label = { $count ->
    [one] 1 connection
   *[other] { $count } connections
}{ $troubled ->
    [0] , all well
    [one] , 1 to look at
   *[other] , { $troubled } to look at
}

## What it does and intends
home-doing = What it does, what it intends
home-now = now
home-next = next
home-task-starting = starting
home-talking = Talking with { $people } · { $where }
home-talking-someone = Conversation under way · { $where }
home-nothing-now = Nothing under way: it waits to be spoken to.
home-quiet-now = Silence until { $until }: nothing is said aloud, unless urgent.
home-quiet-later = Quiet hours from { $from } to { $to }.
home-main-room = main room: { $room }
home-watch-triggered = triggered
home-watch-waiting = waiting on { $sources }
home-nothing-next = Nothing planned.

## Its day
home-day = Its day
home-all-journal = the whole journal
home-day-marks = { $count ->
    [0] Nothing yet today
    [one] 1 moment today
   *[other] { $count } moments today
}
home-mark-conversation = { $time }: conversation with { $people } ({ $count ->
    [one] 1 turn
   *[other] { $count } turns
})
home-mark-delivery = { $time }: spoke to { $people } ({ $where })
home-mark-task = { $time }: task handed over
home-mark-watch = { $time }: a watch fired
home-mark-memory = { $time }: remembered something
home-mark-problem = { $time }: a failure
home-legend-conversation = { $count } conversations
home-legend-delivery = { $count } times it spoke up
home-legend-task = { $count } tasks
home-legend-watch = { $count } watches fired
home-legend-memory = { $count } memories
home-legend-problem = { $count } failures
home-legend-quiet = quiet hours

## What needs you, what it knows
home-attention-title = What needs your attention
home-knows = What it knows
home-all-memories = all memories
home-learnt-today = learnt today at { $time }
