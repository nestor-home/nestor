"""Watch triage: which incoming mails match a watch, and which are urgent, per triage algorithm and model."""

from nestor.bench.suites.watch_triage.algorithms import Algorithm, Decision, decide
from nestor.bench.suites.watch_triage.fake import FakeTriageModel
from nestor.bench.suites.watch_triage.suite import TriageKnobs, WatchTriage

suite = WatchTriage()

__all__ = ["Algorithm", "Decision", "FakeTriageModel", "TriageKnobs", "WatchTriage", "decide", "suite"]
