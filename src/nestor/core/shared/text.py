"""Text cut to fit where people read it."""


def shorten(text: str, limit: int) -> str:
    """`text` on one line, cut to `limit` characters with an ellipsis when it is longer."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"
