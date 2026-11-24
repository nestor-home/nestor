"""Text cut to fit where people read it."""


def shorten(text: str, limit: int) -> str:
    """`text` on one line, cut to `limit` characters with an ellipsis when it is longer."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


def byte_size(size: int) -> str:
    """A file's size as people read it: `830 bytes`, `47 KB`, `2.4 MB`."""
    if size < 1024:
        return f"{size} bytes"
    return f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
