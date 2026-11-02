# Changelog

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
