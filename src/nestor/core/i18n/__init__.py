"""Internationalisation: the domain says *what* to tell people as `Message`s; a `Localizer` turns them
into text in the person's language at the edge. No user-facing sentence is written in code."""

from nestor.core.i18n.ports import Localizer
from nestor.core.i18n.types import Locale, Message, negotiate

__all__ = ["Locale", "Localizer", "Message", "negotiate"]
