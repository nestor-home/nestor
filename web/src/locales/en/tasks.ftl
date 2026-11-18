## Tasks: long work handed to executors, from the request to the delivery.

task-running-empty-hint = Hand me something long: comparing offers, preparing a file.
task-since = since
task-unknown = This task does not exist, or no longer does.
task-took = Took
task-cancel = Stop
task-cancel-action = Stop…
task-cancel-title = Stop this task?
task-cancel-description = What is already done is kept.
task-cancel-notice = Stopping task { $id }…
task-story = How it went
task-story-empty = No trace in the journal.
task-error = What went wrong
task-files = { $count ->
    [one] file
   *[other] files
}
task-result = Result
task-asked-in = Asked in
task-conversation-older = a conversation older than the journal
task-delivery = Answer
task-delivered = { $spoken ->
    [yes] Said out loud
   *[no] Written on { $channel }
}{ $room ->
    [none] {""}
   *[other] , in the { $room }
},
task-delivery-pending = The result will reach the person wherever they are.
task-delivery-none = No delivery.
task-now = Right now
task-starting = Starting…
task-steps = Steps
task-stopped-early = Stopped before it gave a result.
task-no-result = It ended without a result.
task-asked-by = Asked by
task-done-by = Given to
task-started = Started
task-about = About this task
