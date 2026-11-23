"""What Nestor costs, as the admin reads it: a period at a glance, broken down and over time, call by call; a
member reads what their own requests cost and nothing else."""

from datetime import timedelta
from pathlib import Path

from nestor.core import ModelType, PersonId, utc_now
from nestor.modules.accounts import Role
from nestor.modules.usage import CallPurpose, CostBasis, Outcome, UsageRecorded

from ....harness import Harness

NOW = utc_now()


def call(
    cost: int | None, person: str | None, *, purpose: CallPurpose = CallPurpose.TURN, days_ago: int = 0
) -> UsageRecorded:
    return UsageRecorded(
        source="usage",
        at=NOW - timedelta(days=days_ago, minutes=1),
        consumer="main",
        kind=ModelType.LANGUAGE,
        provider="openrouter",
        served="anthropic/claude-haiku-4.5",
        units={"input_tokens": 1000, "output_tokens": 50},
        cost_nusd=cost,
        basis=CostBasis.REPORTED if cost is not None else CostBasis.UNKNOWN,
        price="reported" if cost is not None else None,
        duration_ms=700,
        outcome=Outcome.OK,
        purpose=purpose,
        person=PersonId(person) if person else None,
    )


async def test_the_owner_reads_every_call_and_a_member_only_what_their_requests_cost(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        for spent in (
            call(2_000_000, "mathis"),
            call(1_000_000, "mathis", days_ago=2),
            call(500_000, "mathilde"),
            call(None, None, purpose=CallPurpose.WATCH),  # Nestor's own work, of unknown cost
            call(9_000_000, "mathis", days_ago=40),  # before the default 30 days
        ):
            await admin.nestor.journal.publish(spent)
        await admin.account("mathilde", Role.MEMBER, "mathilde")
        owner, member = await admin.api(), await admin.api("mathilde")

        summary = (await owner.get("/api/v1/usage/summary")).json()
        assert (summary["totals"]["cost_nusd"], summary["totals"]["calls"], summary["totals"]["unknown"]) == (
            3_500_000,
            4,
            1,
        )
        assert summary["totals"]["units"] == {"input_tokens": 4000, "output_tokens": 200}
        people = (await owner.get("/api/v1/usage/groups", by="person")).json()["groups"]
        assert [(g["key"], g["person"] and g["person"]["name"], g["totals"]["cost_nusd"]) for g in people] == [
            ("mathis", "Mathis", 3_000_000),
            ("mathilde", "Mathilde", 500_000),
            (None, None, 0),
        ]
        nestor_own = (await owner.get("/api/v1/usage/summary", person="")).json()["totals"]
        assert (nestor_own["calls"], nestor_own["unknown"]) == (1, 1), "an empty value keeps the calls without one"
        days = (await owner.get("/api/v1/usage/series", by="purpose")).json()
        assert sum(g["totals"]["calls"] for p in days["points"] for g in p["groups"]) == 4
        assert days["span"]["every"] == "day"
        page = (await owner.get("/api/v1/usage/calls", limit=3)).json()
        rest = (await owner.get("/api/v1/usage/calls", limit=3, before=page["next_before"])).json()
        assert (len(page["calls"]), len(rest["calls"]), rest["next_before"]) == (3, 1, None)

        hers = (await member.get("/api/v1/usage/summary")).json()["totals"]
        assert (hers["cost_nusd"], hers["calls"]) == (500_000, 1)
        asked = (await member.get("/api/v1/usage/calls", person="mathis")).json()["calls"]
        assert asked == [], "asking for someone else's gives nothing"
        assert [c["person"]["id"] for c in (await member.get("/api/v1/usage/calls")).json()["calls"]] == ["mathilde"]


async def test_each_model_says_how_its_calls_are_valued(tmp_path: Path) -> None:
    async with Harness(tmp_path) as admin:
        prices = (await (await admin.api()).get("/api/v1/usage/prices")).json()
    assert prices["catalogue"] is True
    main = next(p for p in prices["prices"] if p["consumer"] == "main")
    assert (main["kind"], main["local"], main["source"], main["prices"]) == ("language", False, None, {})
