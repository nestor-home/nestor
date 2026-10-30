"""Double and contract suite for the localizer port."""

from nestor.core.i18n import Locale, Localizer, Message


class EchoLocalizer(Localizer):
    """Renders `id(arg=value, …)`: tests can assert which message was chosen without any catalogue."""

    name = "echo-localizer"

    def __init__(self, *locales: str, default: str = "en") -> None:
        self._locales = tuple(Locale(locale) for locale in (locales or (default,)))
        self._default = Locale(default)

    @property
    def locales(self) -> tuple[Locale, ...]:
        return self._locales

    @property
    def default(self) -> Locale:
        return self._default

    def format(self, message: Message, locale: Locale | str | None = None) -> str:
        args = ", ".join(f"{k}={v}" for k, v in sorted(message.args.items()))
        return f"{message.id}({args})" if args else message.id


class LocalizerContract:
    """Behaviour every `Localizer` must show. Implement `localizer()` over catalogues where
    `contract-greeting` is defined in `default` and `other` (with a `$name` argument),
    `contract-count` has plural forms on `$count`, and `contract-default-only` exists only in
    `default`."""

    default = Locale("en")
    other = Locale("fr")

    def localizer(self) -> Localizer:
        raise NotImplementedError

    def test_a_message_is_rendered_in_the_closest_locale_with_its_arguments(self) -> None:
        localizer = self.localizer()
        greeting = Message.of("contract-greeting", name="Mathis")
        in_other = localizer.format(greeting, f"{self.other}-XX")
        in_default = localizer.format(greeting, "zz")
        assert "Mathis" in in_other and "Mathis" in in_default and in_other != in_default

    def test_plurals_follow_the_count(self) -> None:
        localizer = self.localizer()
        one = localizer.format(Message.of("contract-count", count=1), self.default)
        many = localizer.format(Message.of("contract-count", count=3), self.default)
        assert one != many and "3" in many

    def test_missing_messages_fall_back_without_raising(self) -> None:
        localizer = self.localizer()
        assert localizer.format(Message.of("contract-default-only"), self.other) == localizer.format(
            Message.of("contract-default-only"), self.default
        )
        assert localizer.format(Message.of("contract-nowhere"), self.other) == "contract-nowhere"
        assert set(localizer.locales) >= {self.default, self.other} and localizer.default == self.default
