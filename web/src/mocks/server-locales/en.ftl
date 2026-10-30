## The server's own catalogue, copied from Nestor's locales/en/journal.ftl and delivery.ftl (the reference).

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
}: { $subject ->
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
journal-delivered = Message passed on: { $subject ->
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
journal-delivery-failed = Message not passed on: { $subject ->
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
    [yes] Watch { $watch } triggered by “{ $item }” (urgent)
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
journal-satellite-paired = { $proof ->
    [enrollment_code] Satellite { $device } paired with an enrollment code (room “{ $room }”)
   *[device_code] Satellite { $device } paired with its code (room “{ $room }”)
}
journal-detail-allowed = { $count ->
    [0] Allowed: nothing
   *[other] Allowed: { $capabilities }
}
journal-satellite-revoked = Satellite { $device } revoked
journal-satellite-connected = Satellite { $device } connected (room “{ $room }”)
journal-satellite-disconnected = Satellite { $device } disconnected (room “{ $room }”)
journal-satellite-addition-started = { $proof ->
    [enrollment_code] Enrollment code made to add a satellite
   *[device_code] Adding a satellite by the code it presents
}
journal-satellite-addition-completed = Satellite { $device } added
journal-satellite-addition-cancelled = Satellite addition cancelled
journal-satellite-addition-expired = Satellite addition expired unused
journal-satellite-enrollment-refused = { $reason ->
    [expired] { $device } presented an expired enrollment code
    [used] { $device } presented an enrollment code already used
    [cancelled] { $device } presented a cancelled enrollment code
   *[unknown] { $device } presented a wrong enrollment code
}
journal-satellite-identify-requested = { $device } asked to make itself noticed
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

journal-observation-speaker-identified = { $known ->
    [no] Voice not recognised
   *[yes] Voice of { $person } recognised
}
journal-identity-enrolled = Voice profile recorded for { $person }
journal-identity-forgotten = Voice profile of { $person } deleted

journal-behavior-changed = Attitude: { $behavior ->
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

# Why an unprompted message went where it went (initiative/delivery).
delivery-asked-in-writing = asked for it in writing
delivery-quiet-hours = quiet hours: nothing spoken
delivery-no-presence = no presence information: back to the conversation it came from
delivery-away = { $person } is away
delivery-in-room = { $person } is in the { $room }
delivery-room-without-satellite = { $person } is in a room without a satellite
delivery-home-main-satellite = { $person } is home, room unknown: main satellite ({ $room })
delivery-no-satellite = no satellite where { $person } may be
delivery-other = { $reason }

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
error-memory-empty = A memory cannot be empty: forget it instead.
error-invitation-person = A member's or a guest's account belongs to a person of the household.

## Configuration (copied from Nestor's locales/en/config.ftl and errors.ftl)
config-error-missing = { $path }: required.
config-error-extra = { $path }: unknown setting.
config-error-invalid = { $path }: { $detail }
config-error-unknown-kind = { $path }: no plugin “{ $detail }” is installed.
config-error-reference = { $path }: the environment variable { $detail } is not set.
config-error-secret = { $path }: the secret { $detail } is not set.
error-config-unavailable = This instance was not started from a configuration file: there is nothing to edit.
error-no-secret-key = NESTOR_SECRET_KEY is not set: secrets cannot be kept without it.
error-config-invalid = The configuration cannot be used ({ $count ->
    [one] one problem
   *[other] { $count } problems
}): nothing was written.
error-config-history-unknown = This earlier configuration does not exist.
error-secret-in-use = This secret is still used by { $paths }: remove those references first.
error-secret-unknown = This secret is not set.
error-restart-unconfirmed = Confirm the restart: every conversation will be interrupted for a moment.

## Satellites (copied from Nestor's locales/en/errors.ftl)
error-invalid-code = The code is 6 digits, shown or said by the device.
error-pairing-refused = No device is waiting with this code: it is wrong, has expired, or the device is already paired.
error-not-a-device-code-method = This method does not pair with a code typed here.
error-addition-unknown = This addition does not exist.
error-addition-over = This addition is over: the device is paired, or it was cancelled or has expired.
error-too-many-additions = Too many additions are in progress. Cancel one first.
error-pending-unknown = No device is waiting with this request any more.
error-identify-unsupported = This device cannot make itself noticed.
error-satellite-offline = This satellite is not connected right now.
error-satellite-unknown = This satellite is not (or no longer) paired.
