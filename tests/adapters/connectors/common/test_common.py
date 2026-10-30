"""What mail connectors share: readable text out of mail, and retry pacing."""

import asyncio

import pytest

from nestor.adapters.connectors.common import Backoff, Retry, cap, decode_header_value, html_to_text, tidy
from nestor.core import ProviderError


def test_backoff_doubles_up_to_its_ceiling_and_starts_over_after_a_success() -> None:
    backoff = Backoff(1.0, 5.0)
    assert [backoff.next() for _ in range(5)] == [1.0, 2.0, 4.0, 5.0, 5.0]
    backoff.reset()
    assert backoff.next() == 1.0


@pytest.mark.parametrize(("initial", "maximum", "factor"), [(0, 1, 2), (2, 1, 2), (1, 2, 0.5)])
def test_a_backoff_that_would_not_grow_or_never_wait_is_refused(initial: float, maximum: float, factor: float) -> None:
    with pytest.raises(ValueError, match="backoff"):
        Backoff(initial, maximum, factor)


async def test_retry_waits_the_backoff_for_outages_and_the_long_pause_when_the_person_must_act(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    slept: list[float] = []

    async def sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    retry = Retry("mailbox", Backoff(1.0, 8.0), blocked_s=600.0)
    outage, revoked = ProviderError("x", "timeout", transient=True), ProviderError("x", "revoked", transient=False)
    for error in (outage, outage, revoked, revoked, outage):
        await retry.after(error)
    retry.succeeded()
    await retry.after(outage)
    assert slept == [1.0, 2.0, 600.0, 600.0, 4.0, 1.0]
    assert caplog.text.count("paused until the account is reconnected") == 1


def test_html_becomes_its_visible_text_one_block_per_line() -> None:
    html = '<div>Bonjour&nbsp;<b>Mathis</b><img src="x.png"/><hr/>Suivi&#160;: <a href="#">ici</a></div>'
    assert html_to_text(html) == "Bonjour Mathis\nSuivi : ici"


def test_unbalanced_hidden_tags_do_not_hide_the_rest_of_the_mail() -> None:
    assert html_to_text("</style><p>visible</p>") == "visible"


def test_tidy_keeps_paragraphs_but_not_runs_of_blank_lines_or_spaces() -> None:
    assert tidy("  un \t deux \r\n\n\n\n trois  ") == "un deux\n\ntrois"


def test_cap_leaves_short_text_alone_and_says_what_it_cut() -> None:
    assert cap("court", 10) == "court"
    assert cap("abcdefghij", 4) == "abcd\n[truncated: 6 more characters]"


@pytest.mark.parametrize(
    ("raw", "decoded"),
    [
        ("=?utf-8?q?R=C3=A9union_=C3=A0_l'=C3=A9cole?=", "Réunion à l'école"),
        ("=?ISO-8859-1?B?Suly9G1l?= <jerome@free.fr>", "Jérôme <jerome@free.fr>"),
        ("Plain\r\n folded subject", "Plain folded subject"),
        ("=?x-martian?q?abc?=", "=?x-martian?q?abc?="),
    ],
)
def test_headers_are_decoded_as_people_read_them(raw: str, decoded: str) -> None:
    assert decode_header_value(raw) == decoded
