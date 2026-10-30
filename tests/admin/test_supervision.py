"""Why the assistant spoke: every reason its delivery policy gives has a sentence in every language."""

from datetime import UTC, datetime

import pytest

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.admin.presentation import subject
from nestor.core import PersonId
from nestor.core.i18n import Message
from nestor.modules.channels import Address, Medium
from nestor.modules.home import Granularity
from nestor.modules.household import Person
from nestor.modules.initiative import (
    DeliveryPolicy,
    QuietHours,
)
from nestor.testing.channels import InMemoryChannel
from nestor.testing.home import StaticPresence

MATHIS = PersonId("mathis")
TELEGRAM = Address("telegram", "42")
NOON = datetime(2026, 10, 30, 11, 0, tzinfo=UTC)


class Satellite(InMemoryChannel):
    medium = Medium.SPOKEN

    def __init__(self, channel_id: str, room: str) -> None:
        super().__init__(channel_id)
        self.room = room


def plans() -> list[Message]:
    """Every reason the real delivery policy gives, so a new wording shows up here."""
    person = Person(id=MATHIS, name="Mathis", reach=Address("telegram", "main"))
    channels = [Satellite("voice", "salon"), InMemoryChannel("telegram")]
    presences = [
        StaticPresence().set("mathis", home=False),
        StaticPresence(Granularity.PERSON_ROOM).set("mathis", home=True, room="salon"),
        StaticPresence(Granularity.PERSON_ROOM).set("mathis", home=True, room="garage"),
        StaticPresence().set("mathis", home=True),
        StaticPresence().set("mathis", home=None),
    ]
    policy = DeliveryPolicy(main_room="salon")
    reasons = [
        DeliveryPolicy().plan(person, channels=channels, presence=None, origin=None, now=NOON).reason,
        policy.plan(person, channels=channels, presence=None, origin=None, now=NOON, written=True).reason,
        DeliveryPolicy(quiet_hours=QuietHours.parse("00:00-23:59"))
        .plan(person, channels=channels, presence=presences[0].presence(), origin=None, now=NOON)
        .reason,
        DeliveryPolicy()
        .plan(person, channels=channels, presence=presences[3].presence(), origin=None, now=NOON)
        .reason,
    ]
    reasons += [
        policy.plan(person, channels=channels, presence=p.presence(), origin=None, now=NOON).reason for p in presences
    ]
    return list({repr(r): r for r in reasons}.values())


@pytest.mark.parametrize("locale", ["en", "fr-FR"])
@pytest.mark.parametrize("reason", plans(), ids=lambda m: m.id)
def test_every_delivery_reason_of_the_policy_has_its_sentence_in_each_language(reason: Message, locale: str) -> None:
    said = FluentLocalizer(catalogue_dirs(["nestor"])).format(reason, locale)
    assert said != reason.id and all(str(v) in said for v in reason.args.values())


def test_a_delivery_subject_becomes_arguments_and_an_unknown_one_is_kept() -> None:
    assert subject("task 3f2a1c completed") == {
        "subject": "task",
        "id": "3f2a1c",
        "status": "completed",
        "follow_up": "no",
        "about": "task 3f2a1c completed",
    }
    assert subject("watch 9d81 (follow-up)")["follow_up"] == "yes"
    assert subject("anniversaire")["subject"] == "other"
