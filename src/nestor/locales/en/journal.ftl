# The admin's journal: one sentence per event (`journal-*`), its detail (`journal-detail-*`) and its kind.
# Plugins ship `journal-<event type, dots and underscores as dashes>` for their own events.

journal-other = { $type }

journal-user-said = { $known ->
    [no] Someone said
   *[yes] { $by ->
        [voice] { $person } said (voice recognised)
        [said] { $person } said (name given)
       *[other] { $person } said
    }
}
journal-notification-turn = For { $assistant }: { journal-subject }
journal-assistant-answered = { $assistant } answered
journal-assistant-interrupted = { $assistant } answered (interrupted)
journal-fallback = Fallback answer: { $reason ->
    [model_unavailable] model unavailable
    [model_slow] model too slow
    [recognition_unavailable] speech recognition unavailable
    [synthesis_unavailable] speech synthesis unavailable
   *[other] { $reason }
}
journal-answer-cut = Answer interrupted
journal-model-fell-back = { $model } failed: { $fallback } takes over
journal-conversation-titled = Conversation titled “{ $title }”
journal-answer-voiced = { $assistant } answered with a voice message
journal-answer-files = { $count ->
    [one] { $assistant } sent a file with its answer
   *[other] { $assistant } sent { $count } files with its answer
}
journal-detail-heard = Heard: { $heard }

journal-tool-called = Tool { $tool } called
journal-tool-completed = Tool { $tool } finished in { NUMBER($seconds, maximumFractionDigits: 1) } s
journal-tool-failed = Tool { $tool } failed
journal-tool-deferred = Tool { $tool } still running: its result will come back
journal-tool-returned = Tool { $tool } answered after { NUMBER($seconds, maximumFractionDigits: 0) } s
journal-tool-returned-failed = Tool { $tool } failed after { NUMBER($seconds, maximumFractionDigits: 0) } s
journal-tool-result-stored = Long result kept aside ({ NUMBER($size) } characters)
journal-tool-result-delivered = Result of tool { $tool } passed on

journal-task-started = Task { $task } handed to { $executor }
journal-task-attached = Task { $task } picked up by the executor
journal-task-progressed = Task { $task }: new step
journal-task-cancel-requested = Cancellation requested for task { $task }
journal-task-ended = Task { $task } { $status ->
    [completed] completed
    [failed] failed
    [cancelled] cancelled
   *[other] { $status }
} ({ NUMBER($seconds, maximumFractionDigits: 0) } s)
journal-task-delivered = Result of task { $task } passed on

journal-subject = { $subject ->
    [task] task { $id } { $status ->
        [completed] completed
        [failed] failed
        [cancelled] cancelled
       *[other] { $status }
    }
    [watch] watch { $id }
    [schedule] reminder { $id }
    [tool] result of a tool{ $status ->
        [failed] {" "}(failed)
       *[other] {""}
    }
    [message] message { $id }{ $status ->
        [undelivered] {" "}not delivered
       *[other] {""}
    }
   *[confirmation] confirmation { $id }{ $status ->
        [done] {" "}carried out
       *[other] {""}
    }
}{ $follow_up ->
    [yes] {" "}(follow-up)
   *[no] {""}
}
journal-delivery-considered = { $known ->
    [no] Message
   *[yes] Message for { $person }
}: { journal-subject }
journal-delivered = Message passed on: { journal-subject }
journal-delivery-withheld = Nothing to tell: { journal-subject }
journal-message-requested = { $kind ->
    [question] Question from { $by } for { $to }
    [answer] Answer from { $by } for { $to }
   *[other] Message from { $by } for { $to }
}
journal-message-delivered = Message { $id } delivered
journal-message-undelivered = Message { $id } not delivered
journal-delivery-failed = Message not passed on: { journal-subject }
journal-detail-plan = Planned: { $way ->
    [spoken] aloud on { $spoken }
    [written] in writing on { $written }
    [both] aloud on { $spoken }, then in writing on { $written }
   *[none] nowhere
}
journal-detail-tried = { $count ->
    [0] Tried: no channel available
   *[other] Tried: { $tried }
}

journal-schedule-created = { $recurring ->
    [yes] Regular wake-up set
   *[no] Wake-up set
}
journal-schedule-fired = Wake-up { $id } fired
journal-schedule-cancelled = Wake-up { $id } cancelled
journal-watch-created = Watch created: { $what }
journal-watch-sorted = { $unsorted ->
    [yes] “{ $item }” not sorted: the model did not answer
   *[no] { $matched ->
        [0] “{ $item }” checked against { $asked } { $asked ->
            [one] watch
           *[other] watches
        }: none match
       *[other] “{ $item }” checked against { $asked } { $asked ->
            [one] watch
           *[other] watches
        }: { $matched } matched
    }
}
journal-watch-triggered = { $urgent ->
    [yes] Watch { $watch } triggered by “{ $item }” (urgent)
   *[no] Watch { $watch } triggered by “{ $item }”
}
journal-watch-ended = Watch { $watch } { $reason ->
    [matched] triggered
    [expired] expired
    [cancelled] cancelled
   *[other] { $reason }
}

journal-memory-recorded = { $drawn ->
    [yes] Memory drawn from a conversation
   *[no] Memory recorded
}
journal-memory-corrected = Memory corrected
journal-memory-forgotten = Memory forgotten
journal-episode-summarized = { $kept ->
    [yes] Conversation summarized
   *[no] Conversation with nothing to keep
}

journal-connection-created = Account { $account } connected ({ $kind })
journal-connection-changed = Connection { $connection } { $status ->
    [connected] connected
    [needs_reauth] needs reauthorising
    [error] in error
   *[other] { $status }
}
journal-connection-removed = Connection { $connection } removed

journal-presence-changed = { $where ->
    [away] { $person } is no longer home
    [room] { $person } is in the { $room }
    [home] { $person } is home
   *[unknown] { $person }: location unknown
}

journal-satellite-pairing-requested = Satellite { $device } ({ $model }, { $room }) asks to pair
journal-detail-declares = { $count ->
    [0] Declares: no capability
   *[other] Declares: { $capabilities }
}
journal-satellite-paired = { $proof ->
    [enrollment_code] Satellite { $device } paired with an enrollment code ({ $room })
   *[device_code] Satellite { $device } paired with its code ({ $room })
}
journal-detail-allowed = { $count ->
    [0] Allowed: no capability
   *[other] Allowed: { $capabilities }
}
journal-satellite-revoked = Satellite { $device } revoked
journal-satellite-connected = Satellite { $device } connected ({ $room })
journal-satellite-disconnected = Satellite { $device } disconnected ({ $room })
journal-detail-software = { $name } { $version }
journal-satellite-update-requested = { $device }: update from { $running } to { $target } requested
journal-satellite-update-reported = { $state ->
    [available] { $device }: version { $target } available
    [installing] { $device } is installing { $target }
    [failed] { $device }: { $target } failed, back to the previous version
   *[current] { $device } is up to date
}
journal-satellite-addition-started = { $proof ->
    [enrollment_code] Enrollment code created for a satellite
   *[device_code] Adding a satellite by its code
}
journal-satellite-addition-completed = Satellite { $device } added
journal-satellite-addition-cancelled = Satellite addition cancelled
journal-satellite-addition-expired = Satellite addition expired
journal-satellite-enrollment-refused = { $reason ->
    [expired] { $device } presented an expired enrollment code
    [used] { $device } presented an already used enrollment code
    [cancelled] { $device } presented a cancelled enrollment code
   *[unknown] { $device } presented a wrong enrollment code
}
journal-satellite-identify-requested = { $device }: identify requested
journal-person-detected = { $count ->
    [one] { $count } person seen by { $device } ({ $room })
   *[other] { $count } people seen by { $device } ({ $room })
}
journal-detail-confidence = Confidence: { NUMBER($confidence, style: "percent") }
journal-speech-activity = { $active ->
    [yes] Speech detected near { $device } ({ $room })
   *[no] Speech ended near { $device } ({ $room })
}

journal-account-created = Account { $login } created ({ role-name })
journal-account-role-changed = Account { $login }: role { role-name }
journal-account-disabled = Account { $login } disabled
journal-account-enabled = Account { $login } re-enabled
journal-account-password-changed = Password of { $login } changed
journal-account-locale-changed = { $chosen ->
    [no] Account { $login }: household language
   *[yes] Account { $login }: language { $locale }
}
journal-account-invited = { $known ->
    [no] Invitation ({ role-name })
   *[yes] Invitation ({ role-name }) for { $person }
}
journal-invitation-revoked = Invitation { $invitation } withdrawn
journal-login-succeeded = { $login } signed in
journal-login-failed = { $known ->
    [no] Sign-in refused: { $reason ->
        [wrong-password] wrong password
        [unknown-login] unknown login
        [disabled] account disabled
       *[other] { $reason }
    }
   *[yes] Sign-in refused to account { $login }: { $reason ->
        [wrong-password] wrong password
        [unknown-login] unknown login
        [disabled] account disabled
       *[other] { $reason }
    }
}

journal-speaker-declared = { $person } gave their name
journal-voice-enrolled = { $person }'s voice recorded ({ $where })
journal-voice-forgotten = { $learned ->
    [yes] Learning of { $person }'s voice erased
   *[no] { $person }'s voice erased
}
journal-voice-learning = { $learning ->
    [yes] Learning of { $person }'s voice turned on
   *[no] Learning of { $person }'s voice turned off
}
journal-confirmation-requested = Confirmation requested in writing from { $person }: { $tool }
journal-confirmation-answered = { $approved ->
    [yes] Confirmed in writing
   *[no] Refused in writing
}

journal-behavior-changed = State: { $behavior ->
    [idle] at rest
    [listening] listening
    [thinking] thinking
    [speaking] speaking
   *[other] { $behavior }
}
journal-expression-requested = Expression: { $expression ->
    [joy] joy
    [sigh] sigh
    [thoughtful] thoughtful
    [whisper] whisper
    [excited] excited
    [ahem] ahem
   *[other] { $expression }
}

journal-config-changed = { $restored ->
    [yes] Earlier configuration restored { $via ->
        [cli] from the command line
       *[admin] by { $login }
    }
   *[no] Configuration changed { $via ->
        [cli] from the command line
       *[admin] by { $login }
    }
}
journal-detail-settings = { $count ->
    [one] Setting: { $paths }
   *[other] Settings: { $paths }
}
journal-secret-changed = { $removed ->
    [yes] Secret { $name } deleted
   *[no] Secret { $name } set
} { $via ->
    [cli] from the command line
   *[admin] by { $login }
}
journal-system-restart-requested = Restart requested { $via ->
    [cli] from the command line
   *[admin] by { $login }
}
journal-system-update-requested = Update from { $running } to { $target } requested { $via ->
    [cli] from the command line
   *[admin] by { $login }
}
journal-system-update-failed = { $target } failed to install: Nestor stays on its version
