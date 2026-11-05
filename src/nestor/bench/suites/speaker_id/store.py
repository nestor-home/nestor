"""Voiceprints kept in memory, for a bench run: a voice is enrolled, learned and scored as in the house, without a
database to set up; and a journal that keeps nothing, since a run's enrollments are thrown away."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from datetime import datetime

from nestor.core import Event, PersonId
from nestor.modules.identity import Learned, Profile, Vector, VoiceprintStore, VoiceSpace
from nestor.modules.journal import Entry, EventLog, LogQuery


class Unlogged(EventLog):
    """Takes every event and keeps none."""

    name = "unlogged"

    def __init__(self) -> None:
        self.appended = 0

    async def append(self, event: Event) -> int:
        self.appended += 1
        return self.appended

    async def read(self, query: LogQuery) -> list[Entry]:
        return []


class MemoryVoiceprints(VoiceprintStore):
    name = "memory-voiceprints"

    def __init__(self) -> None:
        self._profiles: dict[PersonId, tuple[str, Profile]] = {}  # by person: the space id, the profile

    async def profiles(self, space: VoiceSpace) -> Mapping[PersonId, Profile]:
        return {person: profile for person, (kept, profile) in self._profiles.items() if kept == space.id}

    async def enroll(
        self, person: PersonId, space: VoiceSpace, anchor: Sequence[Vector], *, learning: bool, at: datetime
    ) -> None:
        self._profiles[person] = (space.id, Profile(anchor=tuple(anchor), learning=learning, enrolled_at=at))

    async def learn(self, person: PersonId, sample: Learned, *, keep: int, per_room: int) -> None:
        space, profile = self._profiles[person]
        learned = sorted((*profile.learned, sample), key=lambda s: s.at)
        kept: list[Learned] = []
        rooms: dict[str, int] = {}
        for found in reversed(learned):  # the newest first: the oldest go beyond the limits
            if rooms.get(found.room, 0) < per_room and len(kept) < keep:
                rooms[found.room] = rooms.get(found.room, 0) + 1
                kept.append(found)
        self._profiles[person] = (space, replace(profile, learned=tuple(reversed(kept))))

    async def unlearn(self, turns: Collection[str]) -> frozenset[PersonId]:
        changed = set()
        for person, (space, profile) in self._profiles.items():
            left = tuple(s for s in profile.learned if s.turn not in turns)
            if len(left) != len(profile.learned):
                self._profiles[person] = (space, replace(profile, learned=left))
                changed.add(person)
        return frozenset(changed)

    async def set_learning(self, person: PersonId, learning: bool) -> None:
        space, profile = self._profiles[person]
        self._profiles[person] = (space, replace(profile, learning=learning))

    async def forget(self, person: PersonId, *, learned_only: bool = False) -> None:
        if learned_only:
            space, profile = self._profiles[person]
            self._profiles[person] = (space, replace(profile, learned=()))
        else:
            self._profiles.pop(person, None)

    async def keep_only(self, space: VoiceSpace) -> None:
        self._profiles = {p: (s, profile) for p, (s, profile) in self._profiles.items() if s == space.id}
