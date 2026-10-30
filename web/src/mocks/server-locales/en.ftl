## What the mock server renders in English, as Nestor's own `.ftl` will (server-owned messages).

journal-presence-room = { $name } is in the { $room }
journal-presence-away = { $name } left home
journal-person-detected = { $count ->
    [one] 1 person seen
   *[other] { $count } people seen
} by { $device } ({ $room })
journal-speech-detected = Speech near { $device } ({ $room })
journal-user-said = { $name } said
journal-assistant-answered = { $assistant } answered
journal-assistant-interrupted = { $assistant } answered (interrupted)
journal-answer-cut = Answer cut by { $name }
journal-fallback = Fallback answer: { $reason ->
    [model_slow] model too slow
    [model_unavailable] model unavailable
   *[other] { $reason }
}
journal-tool-called = Tool { $tool } called
journal-tool-done = Tool { $tool } done in { $duration }
journal-tool-failed = Tool { $tool } failed
journal-task-started = Task { $task } handed to { $executor }
journal-task-progressed = Task { $task }: new step
journal-task-completed = Task { $task } completed ({ $duration })
journal-task-failed = Task { $task } failed ({ $duration })
journal-watch-created = Watch created: { $what }
journal-watch-triggered = Watch { $watch } triggered by “{ $item }”
journal-watch-triaged = Triage: relevant for { $name }
journal-watch-triaged-urgent = Triage: relevant, to report today
journal-subject = { $subject ->
    [task] task { $ref }{ $done ->
        [yes] {" "}completed
       *[no] {""}
    }
    [watch] watch { $ref }
   *[other] { $ref }
}
journal-delivery-considered = Decided to { $written ->
    [yes] write to
   *[no] speak to
} { $name } — { journal-subject }{ $follow_up ->
    [yes] {" "}(follow-up)
   *[no] {""}
}
journal-delivered = Message delivered { $spoken ->
    [yes] out loud
   *[no] in writing
} — { journal-subject }{ $follow_up ->
    [yes] {" "}(follow-up)
   *[no] {""}
}
journal-delivery-failed = Message not delivered{ $spoken ->
    [yes] {" "}out loud
   *[no] {""}
} — { journal-subject }
journal-connection-needs-reauth = Connection { $account } needs reauthorisation
journal-connection-created = Account { $account } connected ({ $service })
journal-pairing-requested = Satellite { $device } ({ $model }, { $room }) asks to pair
journal-memory-recorded = Memory recorded

reason-in-room = { $name } is in the { $room }
reason-away = { $name } is not home
reason-no-presence = no presence information: back to the conversation it came from
reason-no-reply-away = no reply for { $minutes } min, and { $name } is not home

error-bad-credentials = Wrong address or password.
error-account-disabled = This account is disabled: ask the household's owner.
error-session-expired = Your session has expired: sign in again.
error-csrf = This form has expired: reload the page.
error-invitation-unknown = This invitation does not exist, has expired or was already used.
error-weak-password = The password must be at least { $min } characters long.
error-account-exists = An account already exists for this address.
error-last-owner = The household must keep at least one active owner.
error-resource-not-found = { $what } not found.
error-client-incomplete = Enter the OAuth client's ID and secret.
error-client-missing = Register the OAuth client first.
error-fields-missing = Missing fields: { $fields }.
error-provider-refused = The service refused the connection: the server rejected the credentials.
error-pairing-refused = No device is waiting for this code: it is wrong or has expired.
error-memory-empty = A memory cannot be empty: forget it instead.
error-invitation-person = A member's or a guest's account belongs to a person of the household.
