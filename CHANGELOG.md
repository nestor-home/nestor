# Changelog

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
