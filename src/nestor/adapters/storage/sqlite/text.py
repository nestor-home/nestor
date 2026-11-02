"""Full-text search with FTS5: what a person types, as a query that never becomes FTS syntax."""

import re

_WORD = re.compile(r"\w{2,}")


def match(query: str) -> str | None:
    """Any of the words of `query`, each as a prefix (`portail*`), quoted; None when it has no word."""
    terms = _WORD.findall(query)
    return " OR ".join(f'"{t}"*' for t in terms) if terms else None
