## Today: the agent right now, what it perceives, does, intends, did and knows.

home-greeting-night = Good night
home-greeting-day = Hello
home-greeting-evening = Good evening
home-hello = { $greeting }, { $name }.
home-figure-label = { $agent }, { $state }. See the journal.

## What it is doing
home-state-listening = listening
home-state-thinking = thinking
home-state-speaking = speaking
home-state-laughing = laughing
home-state-working = working
home-state-concerned = concerned
home-state-sleeping = resting
home-state-idle = available
home-state-degraded = running degraded

## What it says, in the first person
home-say-delivered = I just spoke to { $people } ({ $where }).
home-say-listening = I'm listening to { $people } ({ $where }).
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

## The columns
home-needs = What I need from you
home-house = The house
home-room-nobody = nobody
home-room-offline = { $count ->
    [one] device offline
   *[other] { $count } devices offline
}
home-away = Out
home-now = Right now
home-task-starting = starting
home-talking = Talking with { $people }
home-talking-someone = Conversation under way
home-nothing-now = Nothing under way. I'm waiting to be spoken to.
home-next = Coming up
home-quiet-now = Silence until { $until }, unless urgent.
home-quiet-later = Quiet hours from { $from } to { $to }.
home-watch-triggered = triggered

## Its day, what it knows
home-today = Today
home-today-empty = Nothing yet today.
home-moment-conversation = Conversation with { $people } ({ $count ->
    [one] 1 turn
   *[other] { $count } turns
})
home-moment-conversation-someone = Conversation ({ $count ->
    [one] 1 turn
   *[other] { $count } turns
})
home-all-journal = The whole journal
home-knows = What I know
home-all-memories = All memories
home-learnt-today = learnt today at { $time }
