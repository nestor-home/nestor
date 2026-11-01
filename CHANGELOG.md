# Changelog

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
