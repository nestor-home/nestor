# The admin's journal: one sentence per event (`journal-*`), its detail (`journal-detail-*`) and its kind.
# Plugins ship `journal-<event type, dots and underscores as dashes>` for their own events.

journal-other = { $type }
journal-kind = { $kind ->
    [conversation] Conversations
    [delivery] Unprompted messages
    [tool] Tools
    [task] Tasks
    [watch] Watches
    [memory] Memories
    [connection] Connections
    [presence] Presence
    [satellite] Satellites
    [observation] Observations
    [account] Accounts
   *[other] Other
}

journal-user-said = { $known ->
    [no] Someone said
   *[yes] { $person } said
}
journal-assistant-answered = { $assistant } answered
journal-assistant-interrupted = { $assistant } answered (interrupted)
journal-fallback = Fallback answer: { $reason ->
    [model_unavailable] model unavailable
    [model_slow] model too slow
    [recognition_unavailable] speech recognition unavailable
    [synthesis_unavailable] speech synthesis unavailable
   *[other] { $reason }
}
journal-answer-cut = Answer cut off by the person
journal-detail-heard = Heard: { $heard }

journal-tool-called = Tool { $tool } called
journal-tool-completed = Tool { $tool } finished in { NUMBER($seconds, maximumFractionDigits: 1) } s
journal-tool-failed = Tool { $tool } failed

journal-task-started = Task { $task } handed to { $executor }
journal-task-attached = Task { $task } followed at the executor
journal-task-progressed = Task { $task }: new step
journal-task-cancel-requested = Stop requested for task { $task }
journal-task-ended = Task { $task } { $status ->
    [completed] completed
    [failed] failed
    [cancelled] cancelled
   *[other] { $status }
} ({ NUMBER($seconds, maximumFractionDigits: 0) } s)
journal-task-delivered = Result of task { $task } passed on

journal-delivery-considered = { $known ->
    [no] Decided to speak up
   *[yes] Decided to speak to { $person }
} — { $subject ->
    [task] task { $id } { $status ->
        [completed] completed
        [failed] failed
        [cancelled] cancelled
       *[other] { $status }
    }
    [watch] watch { $id }
   *[other] { $about }
}{ $follow_up ->
    [yes] {" "}(follow-up)
   *[no] {""}
}
journal-delivered = Message passed on — { $subject ->
    [task] task { $id } { $status ->
        [completed] completed
        [failed] failed
        [cancelled] cancelled
       *[other] { $status }
    }
    [watch] watch { $id }
   *[other] { $about }
}{ $follow_up ->
    [yes] {" "}(follow-up)
   *[no] {""}
}
journal-delivery-failed = Message not passed on — { $subject ->
    [task] task { $id } { $status ->
        [completed] completed
        [failed] failed
        [cancelled] cancelled
       *[other] { $status }
    }
    [watch] watch { $id }
   *[other] { $about }
}{ $follow_up ->
    [yes] {" "}(follow-up)
   *[no] {""}
}
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

journal-watch-created = Watch created: { $what }
journal-detail-keywords = Keywords: { $keywords }
journal-watch-triggered = { $urgent ->
    [yes] Watch { $watch } triggered by “{ $item }” — urgent
   *[no] Watch { $watch } triggered by “{ $item }”
}
journal-watch-ended = Watch { $watch } { $reason ->
    [matched] found
    [expired] expired
    [cancelled] cancelled
   *[other] { $reason }
}

journal-memory-recorded = Memory recorded
journal-memory-corrected = Memory corrected
journal-memory-forgotten = Memory forgotten

journal-connection-created = Account { $account } connected ({ $kind })
journal-connection-changed = Connection { $connection } { $status ->
    [connected] connected
    [needs_reauth] needs to be authorised again
    [error] in error
   *[other] { $status }
}
journal-connection-removed = Connection { $connection } removed

journal-presence-changed = { $where ->
    [away] { $person } is no longer home
    [room] { $person } is in the { $room }
    [home] { $person } is home
   *[unknown] { $person } can no longer be located
}

journal-satellite-pairing-requested = Satellite { $device } ({ $model }, room “{ $room }”) asks to pair
journal-detail-declares = { $count ->
    [0] Declares: nothing
   *[other] Declares: { $capabilities }
}
journal-satellite-paired = Satellite { $device } paired (room “{ $room }”)
journal-detail-allowed = { $count ->
    [0] Allowed: nothing
   *[other] Allowed: { $capabilities }
}
journal-satellite-revoked = Satellite { $device } revoked
journal-satellite-connected = Satellite { $device } connected (room “{ $room }”)
journal-satellite-disconnected = Satellite { $device } disconnected (room “{ $room }”)
journal-person-detected = { $count ->
    [one] { $count } person seen by { $device } (room “{ $room }”)
   *[other] { $count } people seen by { $device } (room “{ $room }”)
}
journal-detail-confidence = Confidence: { NUMBER($confidence, style: "percent") }
journal-speech-activity = { $active ->
    [yes] Speech detected near { $device } (room “{ $room }”)
   *[no] Speech ended near { $device } (room “{ $room }”)
}

journal-account-created = Account { $login } opened ({ role-name })
journal-account-role-changed = Account { $login }: role { role-name }
journal-account-disabled = Account { $login } disabled
journal-account-enabled = Account { $login } enabled again
journal-account-password-changed = Password of account { $login } changed
journal-account-locale-changed = { $chosen ->
    [no] Account { $login } now reads in the household's language
   *[yes] Account { $login } now reads in { $locale }
}
journal-account-invited = { $known ->
    [no] Invitation ({ role-name })
   *[yes] Invitation ({ role-name }) for { $person }
}
journal-invitation-revoked = Invitation { $invitation } withdrawn
journal-login-succeeded = Sign-in of { $login }
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
