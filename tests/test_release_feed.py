"""The release feed the release workflow writes is the one a running Nestor reads."""

import importlib.util
import json
from pathlib import Path
from typing import Any

from nestor.modules.satellites import PROTOCOL
from nestor.modules.system import ChangeKind, Releases

SCRIPT = Path(__file__).parent.parent / "scripts" / "release_feed.py"
CHANGELOG = """# Changelog

## [0.8.0](https://github.com/nestor-home/nestor/compare/v0.7.0...v0.8.0) (2026-11-05)


### ⚠ BREAKING CHANGES

* **satellites:** devices name the software they run ([#44](https://github.com/nestor-home/nestor/issues/44))

### Features

* **satellites:** devices name the software they run ([#44](https://github.com/x)) ([abc1234](https://github.com/y))
* the admin tells when a [newer release](https://nestorhome.dev) is out ([#45](https://github.com/x)) ([def5678](https://github.com/y))


### Bug Fixes

* a fix ([#46](https://github.com/nestor-home/nestor/issues/46)) ([0a1b2c3](https://github.com/nestor-home/nestor/commit/0a1b2c3))

## [0.7.0](https://github.com/nestor-home/nestor/compare/v0.6.0...v0.7.0) (2026-11-03)


### Documentation

* the README follows the satellites channel ([#32](https://github.com/nestor-home/nestor/issues/32)) ([ac35e92](https://github.com/nestor-home/nestor/commit/ac35e92))

## 0.1.0 (2026-10-30)
"""


def _script() -> Any:
    spec = importlib.util.spec_from_file_location("release_feed", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_feed_lists_each_release_with_its_changes_in_plain_text_breaking_ones_once() -> None:
    releases = Releases.from_json(json.loads(json.dumps(_script().feed(CHANGELOG))))
    assert [r.version for r in releases.newer_than("0.6.0")] == ["0.8.0", "0.7.0"]
    latest = releases.latest
    assert latest is not None and latest.breaking
    assert latest.url == "https://github.com/nestor-home/nestor/releases/tag/v0.8.0"
    assert [(c.kind, c.text) for c in latest.changes] == [
        (ChangeKind.BREAKING, "satellites: devices name the software they run"),
        (ChangeKind.FEATURE, "the admin tells when a newer release is out"),
        (ChangeKind.FIX, "a fix"),
    ]
    assert [c.kind for c in releases.releases[1].changes] == [ChangeKind.OTHER]
    assert releases.protocols == {PROTOCOL}


def test_the_changelog_of_this_checkout_makes_a_valid_feed() -> None:
    releases = Releases.from_json(_script().feed((SCRIPT.parent.parent / "CHANGELOG.md").read_text()))
    assert releases.latest is not None


def test_a_change_before_any_section_is_not_counted_in_the_previous_release_s_section() -> None:
    changelog = """## [0.9.0](https://x) (2026-11-06)

### ⚠ BREAKING CHANGES

* models by role

## [0.8.0](https://x) (2026-11-05)

* a loose line
"""
    newest, older = Releases.from_json(_script().feed(changelog)).releases
    assert newest.breaking
    assert [c.kind for c in older.changes] == [ChangeKind.OTHER] and not older.breaking
