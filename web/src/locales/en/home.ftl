## Today: the overview of the household's day.

home-greeting-night = Good night
home-greeting-day = Hello
home-greeting-evening = Good evening
home-hello = { $greeting }, { $name }.
home-summary = Today, { $assistant } held <b>{ $conversations ->
    [one] 1 conversation
   *[other] { $conversations } conversations
}</b>, called <b>{ $tools ->
    [one] 1 tool
   *[other] { $tools } tools
}</b> and spoke up <b>{ $spoken ->
    [one] once
   *[other] { $spoken } times
}</b>.
home-running = { $count ->
    [one] 1 task is running.
   *[other] { $count } tasks are running.
}
home-attention = { $count ->
    [one] 1 thing needs your attention.
   *[other] { $count } things need your attention.
}
home-all-good = Nothing needs your attention.
home-activity = today's activity
home-attention-title = To look at
home-attention-empty = All is well: no connection to reauthorise, no device waiting, no message lost.
home-at-home = At home
home-presence-home = at home
home-presence-away = not home
home-presence-unknown = presence unknown
home-now = Right now
home-now-tasks = tasks
home-now-watches = watches
home-now-satellites = satellites
home-task-starting = starting
home-no-task = No task running.
home-watch-triggered = triggered
home-watch-never = not triggered yet
home-deliveries = Spoken up today
home-all-journal = the whole journal
home-deliveries-empty = It has not spoken up yet today.
home-deliveries-empty-hint = It speaks up by itself when a task ends or a watch finds something.
home-delivered-spoken = out loud
home-delivered-written = in writing on { $channel }
