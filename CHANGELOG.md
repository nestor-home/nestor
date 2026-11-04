# Changelog

## [0.8.1](https://github.com/nestor-home/nestor/compare/v0.8.0...v0.8.1) (2026-11-04)


### Bug Fixes

* back to Python 3.14, the newest every extra installs on ([#65](https://github.com/nestor-home/nestor/issues/65)) ([930e272](https://github.com/nestor-home/nestor/commit/930e27225cd090086bcd1c8e31ca8e1a39ce33d8))

## [0.8.0](https://github.com/nestor-home/nestor/compare/v0.7.0...v0.8.0) (2026-11-04)


### ⚠ BREAKING CHANGES

* satellites name their software and update on request ([#61](https://github.com/nestor-home/nestor/issues/61))

### Features

* install the newest release from the admin ([#60](https://github.com/nestor-home/nestor/issues/60)) ([a8064fc](https://github.com/nestor-home/nestor/commit/a8064fc2803ddbb9d61d3fd97eac74bfd31fecb3))
* satellites name their software and update on request ([#61](https://github.com/nestor-home/nestor/issues/61)) ([c63bc90](https://github.com/nestor-home/nestor/commit/c63bc90db0e3197b7a3a2d0d126345c67405d596))
* the admin says when a newer Nestor is out ([#59](https://github.com/nestor-home/nestor/issues/59)) ([8675d9a](https://github.com/nestor-home/nestor/commit/8675d9a51839041acfd7e6e0566d52427714d095))


### Bug Fixes

* **deps:** update dependency @nestor-home/character to v0.2.0 ([#46](https://github.com/nestor-home/nestor/issues/46)) ([e63a9b5](https://github.com/nestor-home/nestor/commit/e63a9b546419876d53df8f94473cdfbbe74994cb))
* **deps:** update dependency @nestor-home/character to v0.3.0 ([#52](https://github.com/nestor-home/nestor/issues/52)) ([d8bc7c9](https://github.com/nestor-home/nestor/commit/d8bc7c9d207931a478a665c55269531cad71f482))
* **deps:** update dependency @tanstack/react-query to v5.105.3 ([#51](https://github.com/nestor-home/nestor/issues/51)) ([93ec084](https://github.com/nestor-home/nestor/commit/93ec084075798428f2ce49e4fa5baf452584a771))

## [0.7.0](https://github.com/nestor-home/nestor/compare/v0.6.0...v0.7.0) (2026-11-03)


### ⚠ BREAKING CHANGES

* models under names the household chooses, picked by role ([#34](https://github.com/nestor-home/nestor/issues/34))

### Features

* durable wake-ups, so the agent does things later, once or regularly ([#38](https://github.com/nestor-home/nestor/issues/38)) ([4f7aef6](https://github.com/nestor-home/nestor/commit/4f7aef628c41d0481e9117dfea1e13fd88984e34))
* episodes, so the agent remembers past conversations ([#41](https://github.com/nestor-home/nestor/issues/41)) ([9fcd42f](https://github.com/nestor-home/nestor/commit/9fcd42f7c2c5f6d95e059d09d78e87ab6d2264ad))
* instructions in layers, from the stable to this turn's, for the prompt cache ([#35](https://github.com/nestor-home/nestor/issues/35)) ([1b6a54a](https://github.com/nestor-home/nestor/commit/1b6a54aa5215a6660064ee12ece4c9fdcf3b2eb6))
* memories in every turn, found by words and by meaning ([#40](https://github.com/nestor-home/nestor/issues/40)) ([cd138cb](https://github.com/nestor-home/nestor/commit/cd138cb49a56bfb6db1456e279a77ea69c0dd4aa))
* message_person, so the agent passes messages and questions on to the household ([#37](https://github.com/nestor-home/nestor/issues/37)) ([812d564](https://github.com/nestor-home/nestor/commit/812d56444be1b37ac59cfcfe71f97b8edc06e33c))
* models under names the household chooses, picked by role ([#34](https://github.com/nestor-home/nestor/issues/34)) ([03e83bc](https://github.com/nestor-home/nestor/commit/03e83bcff4fbff413039afee428548d348843a6b))


### Bug Fixes

* serve a channel again after it stops, and wait out a second Telegram poller ([#30](https://github.com/nestor-home/nestor/issues/30)) ([905edf6](https://github.com/nestor-home/nestor/commit/905edf62b154ba966b1c813fe797dbf766cb929b))


### Documentation

* the README and compose.yaml follow the satellites channel ([#32](https://github.com/nestor-home/nestor/issues/32)) ([ac35e92](https://github.com/nestor-home/nestor/commit/ac35e9297f05bfba8c6bb67a27923dc97c5ba632))

## [0.6.0](https://github.com/nestor-home/nestor/compare/v0.5.0...v0.6.0) (2026-11-02)


### ⚠ BREAKING CHANGES

* satellites talk in writing, aloud or both ([#27](https://github.com/nestor-home/nestor/issues/27))

### Features

* satellites talk in writing, aloud or both ([#27](https://github.com/nestor-home/nestor/issues/27)) ([6c78d7a](https://github.com/nestor-home/nestor/commit/6c78d7a282c2163e4f36a6941ef60cbd6a0ecb15))
* send each message of an answer as soon as it is written ([#22](https://github.com/nestor-home/nestor/issues/22)) ([6f65676](https://github.com/nestor-home/nestor/commit/6f656764039c91d1514f45346b0a07b4fc1fcc0f))

## [0.5.0](https://github.com/nestor-home/nestor/compare/v0.4.0...v0.5.0) (2026-11-02)


### ⚠ BREAKING CHANGES

* watches sort each item in one model call, without keywords ([#25](https://github.com/nestor-home/nestor/issues/25))

### Features

* nestor bench, with the watch-triage suite ([#23](https://github.com/nestor-home/nestor/issues/23)) ([8938638](https://github.com/nestor-home/nestor/commit/89386380a1c91454442aebe31314da0a5ec0d441))
* watches sort each item in one model call, without keywords ([#25](https://github.com/nestor-home/nestor/issues/25)) ([b19909f](https://github.com/nestor-home/nestor/commit/b19909f3db527e4efeaf151d387a1994e72fa839))

## [0.4.0](https://github.com/nestor-home/nestor/compare/v0.3.0...v0.4.0) (2026-11-01)


### ⚠ BREAKING CHANGES

* existing configurations must change:
    - a French household now sets `persona.locale: fr-FR` (or `fr`),
    `persona.language: French` and `persona.timezone: Europe/Paris`
    explicitly, and the voice channel's `speech.language: fr`;
    - the admin listens on 8470 and the voice channel on 8471 unless
    `admin.port` / the voice `port` are set: keep 8080 / 7860 by setting
    them, or move satellites (pairing URIs, `public_url`), bookmarks,
    proxies and port mappings to the new ports;
    - Docker: compose no longer reads `data/.env` through `env_file` (Nestor
    reads it itself); publish 8470 and 8471 instead of 8080 and 7860;
    - `nestor.adapters.channels.voice` only exports `plugin`,
    `VoiceSettings` and `ElevenLabsSettings`; import the channel from
    `nestor.adapters.channels.voice.channel`;
    - an empty Telegram token, Home Assistant token or ElevenLabs key is now
    a configuration error, as is an empty `api_key` for openrouter.ai,
    openai.com, mistral.ai and anthropic.com;
    - `nestor init` writes `MODEL_API_KEY` (not `OPENROUTER_API_KEY`).

### Features

* run text-only, optional keys, single .env, distinctive ports, English defaults ([#20](https://github.com/nestor-home/nestor/issues/20)) ([40d8dad](https://github.com/nestor-home/nestor/commit/40d8dad98e767d596ef844c32a6fd547a479c65f))

## [0.3.0](https://github.com/nestor-home/nestor/compare/v0.2.0...v0.3.0) (2026-11-01)


### ⚠ BREAKING CHANGES

* existing data folders must be recreated.

### Features

* read the .env next to the configuration ([#16](https://github.com/nestor-home/nestor/issues/16)) ([1ca73a4](https://github.com/nestor-home/nestor/commit/1ca73a428afeaf2566fa7b8c63aea29b7697fcdc))


### Bug Fixes

* give the data folder to the nestor user when the container starts ([#15](https://github.com/nestor-home/nestor/issues/15)) ([ae5f41b](https://github.com/nestor-home/nestor/commit/ae5f41bf7ba3c2a1c3f9ebc9e9a2ccd4df7e6681))


### Code Refactoring

* drop every transition path ([#18](https://github.com/nestor-home/nestor/issues/18)) ([823763c](https://github.com/nestor-home/nestor/commit/823763c4ba73820253afd0bc22572e4bc66ee288))

## [0.2.0](https://github.com/nestor-home/nestor/compare/v0.1.0...v0.2.0) (2026-11-01)


### ⚠ BREAKING CHANGES

* the core accepts only `nestor.satellite/1`. Satellites announcing `nestor.satellite/2` are refused with `protocol_unsupported`, and devices paired under `/2` (Richie's included) no longer authenticate: update their SDK and pair them again.

### Features

* name the satellite protocol nestor.satellite/1 ([#14](https://github.com/nestor-home/nestor/issues/14)) ([ca271be](https://github.com/nestor-home/nestor/commit/ca271be156f0fd96e62dc3b88b744b07daf7a17b))


### Documentation

* point to the developer documentation ([#12](https://github.com/nestor-home/nestor/issues/12)) ([d20e45b](https://github.com/nestor-home/nestor/commit/d20e45bae2109ce3ba29c5d430ba247f0017c66e))

## [0.1.0](https://github.com/nestor-home/nestor/compare/v0.0.2...v0.1.0) (2026-11-01)


### ⚠ BREAKING CHANGES

* the conformance test kit's `Finding.check` and `Finding.detail` are Fluent messages instead of strings, and `ProtocolProbe.run(label=...)` becomes `connection="paired"|"reconnected"|"enrolled"`.

### Features

* check a satellite's conformance from the command line ([#9](https://github.com/nestor-home/nestor/issues/9)) ([474453e](https://github.com/nestor-home/nestor/commit/474453eeb0dba6ab988509aec42438f2bc9ebde9))
* move public URLs to nestorhome.dev ([#11](https://github.com/nestor-home/nestor/issues/11)) ([39b17c8](https://github.com/nestor-home/nestor/commit/39b17c81cf20d98144c8a7e3d31455297ad34a99))

## [0.0.2](https://github.com/nestor-home/nestor/compare/v0.0.1...v0.0.2) (2026-11-01)


### Bug Fixes

* make CI green on Python 3.14 and the satellite sheet test ([#6](https://github.com/nestor-home/nestor/issues/6)) ([139b980](https://github.com/nestor-home/nestor/commit/139b9807b396e2346749dc28ea30e2ca70de5b48))
* publish the package with its admin front, and the image to GHCR ([d36bfd3](https://github.com/nestor-home/nestor/commit/d36bfd3171829000d9149c90b4f101f6a3de36ab))


### Documentation

* stop saying a test keeps the site's character copy identical ([#3](https://github.com/nestor-home/nestor/issues/3)) ([abd5416](https://github.com/nestor-home/nestor/commit/abd54163fc96568a9af807b05cad8148d364a58e))
