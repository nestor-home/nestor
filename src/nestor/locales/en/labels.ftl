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
    [system-read] see what is plugged in
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
    [needs_reauth] to authorise again
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
   *[other] { $auth }
}

capability-audio-capture = microphone
capability-audio-playback = speaker
capability-audio-speech_activity = speech detection
capability-vision-person_detection = person detection (no image sent)
capability-expression-emotion = expressions
capability-motion-head = head movements
capability-device-identify = identify (light, motion or sound)

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
pairing-method-enrollment-provisioning-hint = Give the device the pairing address, in NESTOR_PAIRING_URI or its settings.

# Why a connection needs authorising again, or is in error.
connection-refresh-refused = The service refused to renew the access: it was revoked or has expired. Connect the account again.
connection-no-refresh-token = The access has expired and the service gave no way to renew it. Connect the account again.
connection-reason-other = { $detail }
