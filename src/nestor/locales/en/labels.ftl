# Names of things the admin shows: roles, scopes, statuses, risks, capabilities.
# A capability is `capability-<name, dots as dashes>`: a plugin declaring a new one ships its name.

role-name = { $role ->
    [owner] owner
    [admin] administrator
    [member] member
    [guest] guest
   *[other] { $role }
}
scope-name = { $scope ->
    [accounts-manage] manage accounts
    [accounts-owners-manage] manage owners
    [system-read] see the system status
    [config-manage] edit the configuration and restart
    [household-read] see the household
    [household-connections-manage] manage every connection
    [own-connections-manage] manage one's own connections
    [satellites-manage] pair satellites
    [journal-read-all] read the whole journal
    [journal-read-own] read one's own journal
    [memory-manage-all] manage every memory
    [memory-manage-own] manage one's own memories
    [tasks-manage] manage every task
    [tasks-manage-own] manage one's own tasks
    [watches-manage-all] manage every watch
    [watches-manage-own] manage one's own watches
    [schedules-manage-all] manage every reminder
    [schedules-manage-own] manage one's own reminders
    [messages-read-all] read every message and confirmation
    [messages-read-own] read one's own messages and confirmations
    [media-view] watch the cameras one is allowed
    [media-view-all] watch every camera
    [media-call] call through the satellites one is allowed
    [media-call-all] call through every satellite
    [usage-read-all] see what everything costs
    [usage-read-own] see what one's own requests cost
   *[other] { $scope }
}
invitation-status = { $status ->
    [pending] pending
    [accepted] accepted
    [expired] expired
    [revoked] withdrawn
   *[other] { $status }
}
task-status = { $status ->
    [running] running
    [completed] completed
    [failed] failed
    [cancelled] cancelled
   *[other] { $status }
}
connection-status = { $status ->
    [connected] connected
    [needs_reauth] needs reauthorising
    [error] error
   *[other] { $status }
}
tool-risk = { $risk ->
    [read] read
    [write] write
    [sensitive] sensitive
   *[other] { $risk }
}
auth-kind = { $auth ->
    [oauth2] OAuth
    [secret] credentials
    [none] none
    [discovered] as its server says
   *[other] { $auth }
}

schedule-day = { $day ->
    [mon] Monday
    [tue] Tuesday
    [wed] Wednesday
    [thu] Thursday
    [fri] Friday
    [sat] Saturday
   *[sun] Sunday
}
home-granularity = { $granularity ->
    [home] who is home
    [occupied_rooms] which rooms are occupied
   *[person_room] who is in which room
}

capability-text-input = keyboard
capability-text-display = text on screen
capability-audio-capture = microphone
capability-audio-playback = speaker
capability-audio-speech_activity = speech detection
capability-vision-person_detection = person detection (no image sent)
capability-expression-emotion = expressions
capability-motion-head = head movements
capability-device-identify = identification (light, motion or sound)
capability-device-update = remote updates

# Pairing methods (`pairing-method-<method, dots as dashes>`), and what the person does.
pairing-method-device_code-display = Code on its screen
pairing-method-device_code-display-hint = Type the code the device shows.
pairing-method-device_code-speech = Code said aloud
pairing-method-device_code-speech-hint = Type the code the device says.
pairing-method-enrollment-qr = QR code
pairing-method-enrollment-qr-hint = Show the QR code to the device's camera.
pairing-method-enrollment-input = Code typed on the device
pairing-method-enrollment-input-hint = Type this code on the device.
pairing-method-enrollment-provisioning = Configuration
pairing-method-enrollment-provisioning-hint = Give the pairing URI to the device (NESTOR_PAIRING_URI or its settings).

# Why a connection needs authorising again, or is in error.
connection-refresh-refused = Access revoked or expired. Reconnect the account.
connection-no-refresh-token = Access expired and cannot be renewed. Reconnect the account.
connection-token-refused = The service refused a fresh access. Reconnect the account.

journal-kind = { $kind ->
    [conversation] Conversations
    [delivery] Unprompted messages
    [tool] Tools
    [task] Tasks
    [watch] Watches
    [schedule] Reminders
    [memory] Memories
    [connection] Connections
    [presence] Presence
    [satellite] Satellites
    [voice] Voices
    [observation] Observations
    [account] Accounts
    [usage] Costs
   *[other] Other
}

model-type = { $type ->
    [language] Language models (LLM)
    [embedding] Text embeddings
    [speaker] Speaker recognition
    [transcription] Speech recognition
    [speech] Speech synthesis
    [image] Image generation
   *[other] Other models
}
model-type-help = { $type ->
    [language] To answer, aloud or in writing.
    [embedding] To find memories and past conversations by meaning.
    [speaker] To know who is speaking to a satellite.
    [transcription] To hear what people say to a satellite.
    [speech] To give the assistant its voice.
    [image] To draw the pictures people ask for.
   *[other] { "" }
}

usage-purpose = { $purpose ->
    [turn] answers
    [notification] notifications
    [title] titles
    [watch] watches
    [consolidation] memory
    [indexing] memory search
    [enrollment] voice recording
    [task] tasks
    [search] admin search
    [unattributed] unattributed
   *[other] { $purpose }
}
usage-kind = { $kind ->
    [language] LLM
    [embedding] embedding
    [speaker] voice recognition
    [transcription] transcription
    [speech] speech
    [image] images
   *[other] { $kind }
}
usage-basis = { $basis ->
    [reported] billed
    [priced] estimated
    [free] free
    [unknown] unknown
    [nothing] nothing billed
   *[other] { $basis }
}
usage-outcome = { $outcome ->
    [ok] done
    [failed] failed
    [cancelled] cut short
   *[other] { $outcome }
}
usage-dimension = { $dimension ->
    [consumer] model
    [kind] type
    [provider] provider
    [served] served model
    [purpose] use
    [person] person
    [channel] channel
    [medium] medium
    [basis] cost
    [outcome] outcome
    [origin] origin
    [conversation] conversation
   *[other] { $dimension }
}
usage-unit = { $unit ->
    [input_tokens] input tokens
    [cached_input_tokens] cached tokens
    [cache_write_tokens] cache writes
    [output_tokens] output tokens
    [images] pictures
    [audio_seconds] seconds heard
    [characters] characters spoken
    [requests] calls
   *[other] { $unit }
}
