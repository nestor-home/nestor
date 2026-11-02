"""How the doubles compare text: lower-cased words without accents."""

import unicodedata


def folded_words(text: str) -> list[str]:
    """The words of `text`, lower-cased and without accents, in order: "Végétarienne." → ["vegetarienne"]."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return "".join(c if c.isalnum() else " " for c in plain).split()
