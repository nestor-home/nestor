"""From a request in words to the announcement: the agent is told which feeds and hooks can ring an alert, creates one,
and a new entry of that feed is triaged and announced to the person who asked, an entry nobody waits for is not; a
hook's post rings its alert as it arrives, without the triage model."""

import asyncio
import json
import re
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from nestor.adapters.common.state import StateFile
from nestor.adapters.common.web import FEEDS, PublicWeb
from nestor.adapters.inbound import rss, web_page, webhook
from nestor.adapters.inbound.polled import Watched
from nestor.adapters.inbound.rss import FeedSource
from nestor.core import PersonId
from nestor.modules.channels import Address, InboundMessage, Sender
from nestor.modules.cognition.model import ModelRequest, ToolCall
from nestor.modules.cognition.tools import Toolbox
from nestor.modules.conversation import Agent, Attachments, ModelChoice, Persona
from nestor.modules.household import Account, Household, Person
from nestor.modules.initiative import (
    Alert,
    AlertBook,
    AlertKeeper,
    AlertRang,
    AlertSorted,
    AlertTools,
    Courier,
    RingCause,
    Triage,
)
from nestor.modules.journal import Journal
from nestor.runtime import Nestor
from nestor.runtime.config import parse_config
from nestor.testing.channels import InMemoryChannel
from nestor.testing.cognition import ScriptedModel
from nestor.testing.i18n import EchoLocalizer
from nestor.testing.journal import MemoryBlobStore, MemoryEventLog

from ...runtime.fakes import Fakes
from ...runtime.test_app import CONFIG
from ..dns import resolve
from .rss.feeds import FakeFeed

URL = "https://kernel.example/feed"
TELEGRAM = Address("telegram", "42")
MATHIS = Person(id=PersonId("mathis"), name="Mathis", accounts=(Account.parse("telegram:42"),), reach=TELEGRAM)


def linux_7(request: ModelRequest) -> str:
    """The triage: an entry about Linux 7 matches every alert it is asked about, anything else none."""
    ids = re.findall(r"^- \[([^\]]+)\]", request.messages[0].text, re.MULTILINE)
    if "Linux 7" not in request.messages[-1].text:
        return '{"matches": []}'
    return json.dumps({"matches": [{"alert": id, "summary": "Linux 7.0 est sorti."} for id in ids]})


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeFeed]:
    resolve(monkeypatch, {"kernel.example": "93.184.215.14"})
    feed = FakeFeed()
    feed.add("Linux 6.18")
    with respx.mock(assert_all_called=False) as web:
        web.get(URL).mock(side_effect=feed)
        yield feed


async def test_an_alert_asked_in_words_on_a_feed_is_announced_when_its_entry_comes(
    feed: FakeFeed, tmp_path: Path
) -> None:
    journal, household = Journal(MemoryEventLog()), Household([MATHIS])
    telegram = InMemoryChannel("telegram")
    source = FeedSource("rss", [Watched("Kernel", URL)], PublicWeb(accept=FEEDS), tmp_path / "rss", every_s=0.01)
    book = AlertBook(journal, [source])
    tools = AlertTools(book)
    asked_for = {"title": "Sortie de Linux 7", "instruction": "Préviens Mathis", "frequency": "once"}
    talk = ScriptedModel(
        ToolCall(
            "c1",
            "create_alert",
            {**asked_for, "condition": "la sortie de Linux 7 sur le flux Kernel", "kinds": ["feed"]},
        ),
        "Je te préviens dès que Linux 7 sort.",
        "Linux 7 est sorti !",
    )
    agent = Agent(
        attachments=Attachments(MemoryBlobStore()),
        models=ModelChoice.single(talk),
        persona=Persona(name="Richie", character="Tu es Richie."),
        journal=journal,
        household=household,
        localizer=EchoLocalizer(),
        toolbox=Toolbox(journal, providers=[tools]),
        context=[tools],
    )
    courier = Courier(journal, agent, [telegram])
    triage = ScriptedModel(*[linux_7] * 5)
    keeper = AlertKeeper(book, household, courier, Triage(triage), [source])

    async with courier, book, source, keeper:
        asked = InboundMessage(address=TELEGRAM, sender=Sender("42"), text="Préviens-moi quand Linux 7 sort")
        await agent.respond(asked).collect()
        feed.add("Linux 6.19-rc1")
        feed.add("Linux 7.0 released")
        for _ in range(500):  # until the announcement went out
            if telegram.sent:
                break
            await asyncio.sleep(0.01)

    assert "- feed: Kernel" in talk.requests[0].messages[0].text, "the agent is told which feeds can ring an alert"
    sorted_ = await journal.history(AlertSorted)
    assert [(s.item_title, bool(s.matched)) for s in sorted_] == [
        ("Linux 6.19-rc1", False),
        ("Linux 7.0 released", True),
    ]
    assert telegram.sent == [(TELEGRAM, "Linux 7 est sorti !")]
    assert "Linux 7.0 released" in talk.requests[-1].messages[-1].text


def test_the_configured_feeds_pages_and_hooks_are_what_alerts_can_wait_for_by_name(tmp_path: Path) -> None:
    fakes = Fakes()
    registry = fakes.registry()
    for plugin in (rss.plugin, web_page.plugin, webhook.plugin):
        registry.register(plugin)
    inbound = """
inbound:
  - {kind: rss, feeds: [{name: Kernel, url: "https://www.kernel.org/feeds/kdist.xml"}, {name: LWN, url: "https://lwn.net/headlines/rss"}]}
  - {kind: web-page, pages: [{name: la lampe, url: "https://shop.example/lamp"}]}
  - {kind: webhook, hooks: [{name: github, kind: github, secret: s}, {name: washer, kind: appliance, secret: t}]}
"""
    nestor = Nestor(parse_config(CONFIG.format(data_dir=tmp_path, replies=[]) + inbound, {}), registry)
    assert nestor.alert_book.structured == {"github", "appliance"}, "a hook's kind rings without the triage model"
    assert nestor.alert_book.kinds == {
        "feed": ("Kernel", "LWN"),
        "page": ("la lampe",),
        "github": ("github",),
        "appliance": ("washer",),
    }


async def test_a_post_to_a_hook_rings_its_alert_as_it_arrives_without_the_triage_model(tmp_path: Path) -> None:
    journal, household = Journal(MemoryEventLog()), Household([MATHIS])
    telegram = InMemoryChannel("telegram")
    hook = webhook.Hook(name="lave-vaisselle", kind="dishwasher", secret="s")
    source = webhook.WebhookSource("webhook", [hook], StateFile(tmp_path / "hooks.json"), port=0)
    book = AlertBook(journal, [source])
    talk = ScriptedModel("Le lave-vaisselle a fini.")
    agent = Agent(
        attachments=Attachments(MemoryBlobStore()),
        models=ModelChoice.single(talk),
        persona=Persona(name="Richie", character="Tu es Richie."),
        journal=journal,
        household=household,
        localizer=EchoLocalizer(),
        toolbox=Toolbox(journal),
    )
    courier = Courier(journal, agent, [telegram])
    triage = ScriptedModel()
    keeper = AlertKeeper(book, household, courier, Triage(triage), [source])
    async with courier, book, source, keeper:
        await book.create(
            Alert(title="Lave-vaisselle", instruction="Dis-le à Mathis", kinds=("dishwasher",), owner=MATHIS.id)
        )
        transport = httpx.ASGITransport(app=source.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://nestor") as client:
            posted = await client.post(
                "/hooks/lave-vaisselle", json={"state": "done"}, headers={"Authorization": "Bearer s"}
            )
        assert posted.status_code == 202
        for _ in range(500):  # until the announcement went out
            if telegram.sent:
                break
            await asyncio.sleep(0.01)

    assert triage.requests == []
    (rang,) = await journal.history(AlertRang)
    assert (rang.cause, rang.item_kind) == (RingCause.EVENT, "dishwasher")
    assert telegram.sent == [(TELEGRAM, "Le lave-vaisselle a fini.")]
