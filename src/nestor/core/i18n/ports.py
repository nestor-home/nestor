"""The localizer port."""

from abc import ABC, abstractmethod

from nestor.core.i18n.types import Locale, Message


class Localizer(ABC):
    """Renders messages in a locale.

    Contract (checked by `nestor.testing.i18n.LocalizerContract`):
    - `format` never raises: an unknown locale falls back to the closest available one, then the
      default; a message missing in that locale falls back to the default locale, then to its id;
    - arguments are interpolated, plurals follow the locale's rules;
    - `locales` lists what can really be rendered.
    """

    @property
    @abstractmethod
    def locales(self) -> tuple[Locale, ...]: ...

    @property
    @abstractmethod
    def default(self) -> Locale: ...

    @abstractmethod
    def format(self, message: Message, locale: Locale | str | None = None) -> str: ...
