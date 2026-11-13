# The voice benches: transcription and speech.

bench-transcription-description = how well a transcription model hears French recordings, and how fast
bench-transcription-no-header = the dataset must start with {"{"}"dataset": "transcription", "version": <number>, "audio": <folder>{"}"}
bench-transcription-bad-case = case { $case }: it needs a "text" and a "file" found in the audio folder
bench-transcription-wer = word error rate
bench-transcription-failed = recordings it failed on
bench-transcription-latency-p50 = latency of a recording, median
bench-transcription-latency-p95 = latency of a recording, 95th percentile
bench-transcription-rtf-p50 = real-time factor, median (seconds of work per second of speech)
bench-transcription-cold-start = cold start (loading the model)
bench-transcription-memory = memory added by loading it
bench-transcription-worst = most misheard recordings
bench-transcription-heard = said: { $said } · heard: { $heard }

bench-speech-description = how fast a speech model records a sentence, and how clearly a transcription model hears it back
bench-speech-no-header = the dataset must start with {"{"}"dataset": "speech", "version": <number>{"}"}
bench-speech-bad-case = case { $case }: it needs a "text"
bench-speech-wer = word error rate of the judge on the recordings
bench-speech-failed = sentences it could not record
bench-speech-unheard = recordings the judge could not hear
bench-speech-latency-p50 = latency of a sentence, median
bench-speech-latency-p95 = latency of a sentence, 95th percentile
bench-speech-cold-start = cold start (loading the model)
bench-speech-misheard = sentences the judge misheard
bench-speech-heard = said: { $said } · heard: { $heard }
