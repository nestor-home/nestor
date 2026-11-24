## Tasks: work handed to executors, each a thread of turns that a person can answer, reorient or continue.

task-running-empty-hint = Hand me something long: comparing offers, preparing a file.
task-unknown = This task does not exist, or you cannot see it.
task-starting = Starting…
task-turns = { $count ->
    [one] { $count } turn
   *[other] { $count } turns
}
task-for = for { $name }
task-thread = Thread
task-notes = Notes
task-story = How it went
task-story-empty = No trace in the journal.
task-about = About this task
task-about-state = State
task-asked-by = Asked by
task-asked-in = Asked in
task-done-by = Given to
task-started = Opened
task-steered = given while it worked
task-turn-stopped = Stopped before it came back.
task-turn-empty = Came back without a report.
task-delivered = { $spoken ->
    [yes] Said out loud
   *[no] Written on { $channel }
}{ $room ->
    [none] {""}
   *[other] , in the { $room }
},
task-composer-steer = Reorient the work in progress…
task-composer-steer-hint = Taken into the turn that is working.
task-composer-restart = Give a new instruction…
task-composer-restart-hint = Stops the turn that is working and starts a new one with it.
task-composer-answer = Answer its question…
task-composer-answer-hint = Your answer starts its next turn.
task-composer-continue = Ask for more…
task-composer-continue-hint = Starts a new turn in the same thread.
task-composer-reopen = Ask for more…
task-composer-reopen-hint = Writing to it takes it out of the archive.
task-send = Send
task-steered-notice = Taken into the work in progress.
task-continued-notice = Sent: the task is back at work.
task-write-steer = Reorient…
task-write-steer-title = Reorient the work in progress
task-write-restart = New instruction…
task-write-restart-title = Give a new instruction
task-write-answer = Answer…
task-write-answer-title = Answer the task
task-write-continue = Continue…
task-write-continue-title = Ask for more
task-write-reopen = Continue…
task-write-reopen-title = Ask for more
task-rename-action = Rename…
task-rename-title = Rename the task
task-rename-label = Title
task-rename-save = Rename
task-renamed-notice = Renamed.
task-stop = Stop
task-stop-action = Stop…
task-stop-title = Stop the work in progress?
task-stop-description = The task stays: you can give it a new instruction later.
task-stopped-notice = Stopped.
task-stop-pending-notice = Stop asked: the executor has not confirmed it yet.
task-archive = Archive
task-archive-action = Archive…
task-archive-title = Archive this task?
task-archive-description = { $working ->
    [yes] The work in progress stops first. Writing to it later takes it out of the archive.
   *[no] Writing to it later takes it out of the archive.
}
task-archived-notice = Archived.
