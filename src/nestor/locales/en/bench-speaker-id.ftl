# The speaker-id bench suite: does a voice model tell the household's voices apart, and what it costs.

bench-speaker-id-description = how well a voice model tells voices apart (false accepts first), how learning helps, and what it costs on this machine
bench-speaker-id-no-header = the dataset must start with {"{"}"dataset": "speaker-id", "version": <number>, "audio": <folder>{"}"}, and optionally "enroll", "spare" and "impostors"
bench-speaker-id-no-audio = { $path } must hold one folder of WAV files per speaker, for at least two speakers
bench-speaker-id-unknown = impostors without recordings: { $speakers }
bench-speaker-id-too-few = { $speaker } needs at least { $needed } recordings
bench-speaker-id-bad-audio = { $path } is not a 16-bit WAV file

bench-speaker-id-eer = EER (equal error rate)
bench-speaker-id-threshold = threshold used
bench-speaker-id-far = false accepts at the threshold (pairs of voices)
bench-speaker-id-frr = false rejects at the threshold
bench-speaker-id-threshold-at-far-1 = threshold for 1 % false accepts
bench-speaker-id-frr-at-far-1 = false rejects at that threshold
bench-speaker-id-top1 = closed set: the closest voice is the right one
bench-speaker-id-unrecognised = turns of an enrolled voice left unknown
bench-speaker-id-misheard = turns taken for someone else
bench-speaker-id-impostors-unknown = turns of an unknown voice left unknown
bench-speaker-id-failed = turns without a voiceprint
bench-speaker-id-replay-off-far-first = replay without learning: taken for someone else, first third
bench-speaker-id-replay-off-far-last = replay without learning: taken for someone else, last third
bench-speaker-id-replay-off-frr-first = replay without learning: not recognised, first third
bench-speaker-id-replay-off-frr-last = replay without learning: not recognised, last third
bench-speaker-id-replay-on-far-first = replay with learning: taken for someone else, first third
bench-speaker-id-replay-on-far-last = replay with learning: taken for someone else, last third
bench-speaker-id-replay-on-frr-first = replay with learning: not recognised, first third
bench-speaker-id-replay-on-frr-last = replay with learning: not recognised, last third
bench-speaker-id-learned = turns learned during the replay
bench-speaker-id-retakes = enrollment phrases said again
bench-speaker-id-failed-enrollments = enrollments that failed
bench-speaker-id-cold-start = cold start (loading and first voiceprint)
bench-speaker-id-latency-p50 = voiceprint latency, median
bench-speaker-id-latency-p95 = voiceprint latency, 95th percentile
bench-speaker-id-rtf-p50 = RTF, median (latency per second of speech)
bench-speaker-id-model-size = model on disk
bench-speaker-id-memory = memory added by loading it

bench-speaker-id-taken-list = Voices taken for someone else
bench-speaker-id-taken = { $who } taken for { $whom }: { $times ->
    [one] once
   *[other] { $times } times
} (score up to { $score })
