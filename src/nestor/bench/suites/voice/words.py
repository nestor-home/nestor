"""Word error rate, the measure of speech recognition: the words to insert, delete or replace to turn what was heard
into what was said, over the words said. Case and punctuation do not count; accents do (French tells words apart
by them); a number written in figures by one side and in letters by the other counts as an error."""

import re
from collections.abc import Iterable, Mapping
from typing import Any

_WORD = re.compile(r"\w+")


def words(text: str) -> list[str]:
    """The words of `text`, lower case, punctuation left out: "Rappelle-moi d'acheter" is rappelle, moi, d, acheter."""
    return _WORD.findall(text.casefold())


def errors(said: str, heard: str) -> int:
    """The insertions, deletions and substitutions that turn the words `heard` into those `said` (Levenshtein)."""
    expected, found = words(said), words(heard)
    previous = list(range(len(found) + 1))
    for i, word in enumerate(expected, 1):
        current = [i]
        for j, other in enumerate(found, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (word != other)))
        previous = current
    return previous[-1]


def rate(results: Iterable[Mapping[str, Any]]) -> float | None:
    """The word error rate over the outputs that were heard: their errors over their words."""
    heard = [r for r in results if "errors" in r]
    said = sum(r["words"] for r in heard)
    return sum(r["errors"] for r in heard) / said if said else None
