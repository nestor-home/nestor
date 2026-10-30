## Tasks: long work handed to executors, from the request to the delivery.

task-title = Tasks
task-intro = Long work handed to the executors, from the moment it was asked for to its delivery.
task-running = Running
task-running-empty = No task running.
task-running-empty-hint = Ask for something long: comparing offers, preparing a file.
task-done = Finished
task-done-empty = No finished task.
task-for = for { $name }
task-since = since
task-unknown = This task does not exist, or no longer does.
task-requested-by = asked by { $name }
task-took = took { $duration }
task-cancel = Stop
task-cancel-action = Stop…
task-cancel-title = Stop this task?
task-cancel-description = The executor is told to stop; what is already done stays done.
task-cancel-notice = Stop requested for task { $id }.
task-story = How it went
task-story-empty = The journal keeps no trace of this task.
task-error = error
task-result = result
task-asked-in = asked in
task-a-conversation = a conversation
task-conversation-older = a conversation older than the journal
task-delivery = delivery
task-delivered = { $spoken ->
    [yes] Said out loud
   *[no] Written on { $channel }
}{ $room ->
    [none] {""}
   *[other] , in the { $room }
},
task-delivery-pending = When it ends, the result will be told to the person wherever they are.
task-delivery-none = No delivery.
