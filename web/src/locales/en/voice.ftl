## A person's voice: its state on their page, then the guided recording, where { $assistant } talks to whoever reads.

people-voice = voice
people-voice-none = Not recorded yet.
people-voice-recorded = Recorded
people-voice-learned = { $count ->
    [0] Nothing learned since.
    [one] 1 voiceprint learned since, the last
   *[other] { $count } voiceprints learned since, the last
}
people-voice-not-learning = No longer learns over time.
people-voice-off = Voice recognition is off.
people-voice-off-link = Configuration › Voices
people-voice-record = { $own ->
    [yes] Record my voice
   *[no] Record their voice
}
people-voice-redo = Record again
people-voice-learning = Learn over time
people-voice-learning-on = { $assistant } learns over time again.
people-voice-learning-off = { $assistant } no longer learns over time.
people-voice-forget-learned = Forget what was learned
people-voice-forget-learned-title = Forget what was learned?
people-voice-forget-learned-body = { $count ->
    [one] The voiceprint learned from conversations is erased.
   *[other] The { $count } voiceprints learned from conversations are erased.
} The recording stays.
people-voice-forget = { $own ->
    [yes] Forget my voice
   *[no] Forget their voice
}
people-voice-forget-title = { $own ->
    [yes] Forget your voice?
   *[no] Forget { $name }'s voice?
}
people-voice-forget-body = The recording and everything learned are erased. { $assistant } will no longer recognise { $name } on satellites.
people-voice-forget-confirm = Forget
people-voice-forgotten = Voice forgotten.
people-voice-learned-forgotten = What was learned is forgotten.

recording-description = Four steps for { $assistant } to recognise a voice: consent, microphone, five phrases, a try.
recording-figure = { $assistant }

## 1. Before starting
recording-title = { $own ->
    [yes] Record your voice
   *[no] Record { $name }'s voice
}
recording-keeps = { $own ->
    [yes] I keep a voiceprint of your voice, never the sound.
   *[no] I keep a voiceprint of { $name }'s voice, never the sound.
}
recording-use = It tells me who is talking to the satellites, so I answer with the right reminders, accounts and memories.
recording-not-a-password = It is not a password: for anything sensitive, I always ask for a confirmation.
recording-other-agrees = { $name } reads the phrases, and has to agree.
recording-learning = Learn over time
recording-learning-hint = I refine the voiceprint when I'm sure who is talking, without keeping the sound.
recording-erase = { $own ->
    [yes] Everything is erased from your page, with “Forget my voice”.
   *[no] Everything is erased from { $name }'s page, with “Forget their voice”.
}
recording-start = Start

## 2. The microphone
recording-title-microphone = Say hello
recording-microphone = Microphone
recording-microphone-unnamed = Microphone { $n }
recording-microphone-opening = Opening the microphone…
recording-microphone-say = Say “Hello { $assistant }” to try the microphone.
recording-microphone-clear = I can hear you well.
recording-microphone-quiet = I can barely hear you. Move closer to the microphone, or speak up.
recording-microphone-noisy = It's too noisy around you. Find a quieter spot.
recording-microphone-denied = The browser refuses the microphone. Allow it in the site settings, then try again.
recording-microphone-missing = No microphone found. Plug one in, then try again.
recording-microphone-insecure = The browser only opens the microphone on a secure address: https, or localhost.
recording-microphone-unsupported = This browser gives no access to the microphone.
recording-microphone-failed = The microphone could not open.
recording-retry = Try again
recording-continue = Continue

## 3. Five phrases
recording-title-phrase = Read this phrase
recording-phrase-count = Phrase { $n } of { $total }
recording-phrase = “{ $phrase }”
recording-ring = Phrases kept
recording-listening = I'm listening. No button: I know when you're done.
recording-checking = Checking…
recording-kept = Perfect. Next one.
recording-again = { $problem ->
    [too_short] That was a bit short. Once more?
    [too_quiet] I didn't hear it well. Once more, a little louder?
    [too_loud] That was too loud, or too noisy. Once more?
    [other_voice] That's not the same voice as before. Once more?
   *[other] I didn't hear it well, once more?
}
recording-finishing = Learning your voice…

## 4. Ready
recording-title-done = { $own ->
    [yes] I recognise your voice
   *[no] I recognise { $name }'s voice
}
recording-try = Try it
recording-try-hint = Say something, and I'll tell you who I hear.
recording-try-listening = Say something…
recording-heard = It's { $name }.
recording-heard-nobody = I don't recognise this voice.
recording-likeness = Likeness { $score }%, recognised from { $threshold }%.
recording-satellite = You can also do it again from a satellite, with its real microphone: say “{ $assistant }, learn to recognise my voice”.
recording-done = Done
