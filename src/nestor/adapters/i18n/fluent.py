"""A localizer over Project Fluent catalogues.

Every package may ship `locales/<locale>/*.ftl` next to its code: Nestor itself, and any plugin.
The runtime gathers those folders; later folders may add messages, never silently replace one
(a duplicate id across packages is an error, so a plugin cannot reword the core).
"""

import logging
from collections.abc import Iterable
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from fluent.runtime import FluentBundle, FluentResource
from fluent.syntax.ast import Junk, Resource

from nestor.core import ContractError
from nestor.core.i18n import Locale, Localizer, Message, negotiate

log = logging.getLogger(__name__)
ENGLISH = Locale("en")


def catalogue_dirs(packages: Iterable[str]) -> list[Traversable]:
    """The `locales` folder of each importable package that has one."""
    found: list[Traversable] = []
    for package in dict.fromkeys(packages):
        try:
            folder = files(package) / "locales"
        except ModuleNotFoundError:
            continue
        if folder.is_dir():
            found.append(folder)
    return found


class FluentLocalizer(Localizer):
    def __init__(self, folders: Iterable[Traversable | Path], *, default: Locale = ENGLISH) -> None:
        sources: dict[Locale, list[Resource]] = {}
        texts: dict[Locale, list[str]] = {}
        owners: dict[tuple[Locale, str], str] = {}
        for folder in folders:
            for locale_dir in sorted(folder.iterdir(), key=lambda d: d.name):
                if not locale_dir.is_dir():
                    continue
                locale = Locale(locale_dir.name)
                for catalogue in sorted(locale_dir.iterdir(), key=lambda c: c.name):
                    if catalogue.name.endswith(".ftl"):
                        text = catalogue.read_text(encoding="utf-8")
                        resource = FluentResource(text)
                        _check(resource, locale, catalogue.name, owners)
                        sources.setdefault(locale, []).append(resource)
                        texts.setdefault(locale, []).append(text)
        if default not in sources:
            raise ContractError(f"no catalogue for the default locale {default!r}")
        self._default = default
        self._bundles = {locale: _bundle(locale, resources) for locale, resources in sources.items()}
        self._texts = {locale: "\n".join(parts) for locale, parts in texts.items()}

    @property
    def locales(self) -> tuple[Locale, ...]:
        return tuple(sorted(self._bundles))

    @property
    def default(self) -> Locale:
        return self._default

    def source(self, locale: Locale | str) -> tuple[Locale, str]:
        """The closest locale and its whole catalogue in Fluent syntax, every package's: what a front
        loads to render the messages the server sends (a plugin's included)."""
        chosen = negotiate(locale, self._bundles, self._default)
        return chosen, self._texts[chosen]

    def format(self, message: Message, locale: Locale | str | None = None) -> str:
        chosen = negotiate(locale or self._default, self._bundles, self._default)
        for candidate in dict.fromkeys((chosen, self._default)):
            bundle = self._bundles[candidate]
            if not bundle.has_message(message.id):
                continue
            pattern = bundle.get_message(message.id).value
            if pattern is None:
                continue
            text, errors = bundle.format_pattern(pattern, dict(message.args))
            for error in errors:
                log.warning("message %s in %s: %s", message.id, candidate, error)
            return str(text)
        log.warning("message %s missing in %s and %s", message.id, chosen, self._default)
        return message.id


def _check(resource: Resource, locale: Locale, name: str, owners: dict[tuple[Locale, str], str]) -> None:
    """Refuse invalid syntax and an id defined twice (a plugin must not reword the core)."""
    for entry in resource.body:
        if isinstance(entry, Junk):
            raise ContractError(f"{locale}/{name}: invalid Fluent syntax near {(entry.content or '')[:60]!r}")
        identifier = getattr(getattr(entry, "id", None), "name", None)
        if identifier is None:
            continue
        if (locale, identifier) in owners:
            raise ContractError(
                f"message {identifier!r} is defined twice in {locale} ({owners[locale, identifier]}, {name})"
            )
        owners[locale, identifier] = name


def _bundle(locale: Locale, resources: Iterable[Resource]) -> FluentBundle:
    bundle = FluentBundle([locale], use_isolating=False)  # no bidi marks around arguments in plain text
    for resource in resources:
        bundle.add_resource(resource)
    return bundle
