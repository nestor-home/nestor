"""Scoring helpers: a yes/no decision against the expected answer, and percentiles."""

import pytest

from nestor.bench import Confusion, percentile


def test_precision_recall_and_f1_of_a_decision() -> None:
    confusion = Confusion()
    for predicted, expected in [(True, True), (True, True), (True, False), (False, True), (False, False)]:
        confusion.add(predicted=predicted, expected=expected)
    assert confusion.precision == pytest.approx(2 / 3)
    assert confusion.recall == pytest.approx(2 / 3)
    assert confusion.f1 == pytest.approx(2 / 3)


def test_a_score_with_nothing_to_measure_it_on_is_unknown_not_zero() -> None:
    nothing_said = Confusion()
    nothing_said.add(predicted=False, expected=True)
    assert (nothing_said.precision, nothing_said.recall, nothing_said.f1) == (None, 0.0, None)
    all_wrong = Confusion(false_positives=1, false_negatives=1)
    assert (all_wrong.precision, all_wrong.recall, all_wrong.f1) == (0.0, 0.0, 0.0)


def test_percentiles_interpolate_between_ranks() -> None:
    assert percentile([], 0.5) is None
    assert percentile([3.0], 0.95) == 3.0
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.5) == 2.5
    assert percentile([float(v) for v in range(1, 101)], 0.95) == pytest.approx(95.05)
