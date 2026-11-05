"""Speaker identification: how well a voice model tells the household's voices apart, and what it costs."""

from nestor.bench.suites.speaker_id.suite import SpeakerId

suite = SpeakerId()

__all__ = ["SpeakerId", "suite"]
