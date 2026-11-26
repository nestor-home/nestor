"""Alert triage: which incoming mails match an alert, per triage algorithm and model."""

from nestor.bench.suites.alert_triage.algorithms import Algorithm, Decision, decide
from nestor.bench.suites.alert_triage.fake import FakeTriageModel
from nestor.bench.suites.alert_triage.suite import AlertTriage, TriageKnobs

suite = AlertTriage()

__all__ = ["AlertTriage", "Algorithm", "Decision", "FakeTriageModel", "TriageKnobs", "decide", "suite"]
