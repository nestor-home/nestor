# The satellite conformance suite (`nestor satellites conformance`): its checks, what it saw instead,
# and the command's own words. A check names the rule of the standard (https://nestorhome.dev/docs/satellites/protocol/) it proves.

## Checks. `$connection`: paired (first connection), reconnected, enrolled (paired with an enrollment code).

conformance-asks-to-pair = asks to pair
conformance-declares-provisioning = declares enrollment.provisioning (P1)
conformance-claims-token = claims its token once its device code is typed (P2)
conformance-polls-after-identify = keeps polling after a pending identify (I1)
conformance-connects = opens its link with its token, a hello first, as the paired device (L1)
conformance-reconnects = reconnects with the same token after the core closes its link (L5)
conformance-connects-enrolled = opens its link after pairing with an enrollment code
conformance-acknowledges = { $connection ->
    [reconnected] after reconnecting: acknowledges { $intent } within { $seconds } s
    [enrolled] enrolled: acknowledges { $intent } within { $seconds } s
   *[paired] acknowledges { $intent } within { $seconds } s
}
conformance-follows-schema = { $connection ->
    [reconnected] after reconnecting: every message follows the schema
    [enrolled] enrolled: every message follows the schema
   *[paired] every message follows the schema
}
conformance-exchanges-audio = exchanges audio, as allowed (A1, A2)
conformance-receives-audio = receives the core's audio (A1, A2)
conformance-sends-audio = sends its microphone audio (A1, A2)
conformance-pairs-again = forgets a refused token and pairs again (L2, P8)
conformance-no-unallowed-audio = offers no audio when audio is not allowed (A1)
conformance-enrolls = pairs with the enrollment code of { $variable }, no code typed (P3, P4)
conformance-falls-back = falls back to a device code after its enrollment code is refused ({ $refusal ->
    [expired] expired
    [used] used
   *[wrong] wrong
}) (P5)
conformance-refused-once = presents a refused enrollment code ({ $refusal ->
    [expired] expired
    [used] used
   *[wrong] wrong
}) only once (P5)
conformance-waits-retry-after = waits for Retry-After when rate-limited (P6)
conformance-pairs-after-limit = pairs once the rate limit lifts (P6)
conformance-runs = runs without crashing

## What was seen instead.

conformance-never-polled-after-identify = never polled past the identify
conformance-no-link = no link within { $seconds } s
conformance-link-refused = link closed with { $code }: { $why }
conformance-no-audio-offer = no audio offer within { $seconds } s
conformance-voice-missing = audio cannot be checked without the voice extra ({ $module } is missing)
conformance-audio-offers = { $count ->
    [one] 1 audio offer
   *[other] { $count } audio offers
}
conformance-never-asked-again = never asked to pair again
conformance-no-ack = no ack with this intent's id
conformance-off-schema = { $errors }
conformance-no-receiver-report = no RTCP receiver report from the satellite
conformance-no-audio-frame = no audio frame from the satellite
conformance-no-token = no token claimed
conformance-no-code-sent = paired without presenting its enrollment code
conformance-tries = { $count ->
    [one] once
   *[other] { $count } times
}
conformance-attempts = attempts at { $times } s
conformance-no-attempt = no attempt
conformance-raised = raised { $error }
conformance-exited = exited with status { $status }

## The command.

conformance-help = check a satellite against nestor.satellite/1 (audio checks need the voice extra)
conformance-description = Check a satellite, written in any language, against the nestor.satellite/1 standard. A fake core (the real pairing service and gateway) launches the satellite's command once per scenario: pairing with a device code, with an enrollment code, refused codes, rate limits, identify, the link and its hello, acks, text, audio both ways when allowed, reconnection and a refused token.
conformance-epilog =
    In the command, { "{url}" } is replaced by the fake core's URL and { "{state}" } by a fresh folder for the satellite's token.
    The scenarios with an enrollment code give it in the NESTOR_PAIRING_URI environment variable (removed in the others), the way a person configures a headless device.
    Exit status: 0 when the satellite conforms, 1 when a check fails, 2 when the command cannot run.
conformance-deadline-help = seconds the satellite has for each step (default: { $seconds })
conformance-command-help = the satellite's command line, after --
conformance-passed = PASS  { $check }
conformance-failed = FAIL  { $check }
conformance-failed-detail = FAIL  { $check } ({ $detail })
conformance-conformant = conformant: { $total } checks passed
conformance-not-conformant = { $count ->
    [one] 1 check failed
   *[other] { $count } checks failed
} out of { $total }
conformance-no-command = nestor: give the satellite's command after --, for example: nestor satellites conformance -- ./my-satellite --core { "{url}" }
conformance-no-program = nestor: { $program } cannot be run (not found, or not executable)
