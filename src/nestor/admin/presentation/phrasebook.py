"""Messages rendered in one reader's locale, and the names of things the admin shows.

What a catalogue lacks falls back to something readable: a capability no catalogue names keeps its
technical name, an event no catalogue describes shows its type.
"""

from nestor.core.i18n import Locale, Localizer, Message


def capability_message(name: str) -> Message:
    """`audio.capture` → `capability-audio-capture`: a plugin declaring a capability ships this id."""
    return Message.of(f"capability-{name.replace('.', '-')}")


class Phrasebook:
    def __init__(self, localizer: Localizer, locale: Locale) -> None:
        self.localizer, self.locale = localizer, locale

    def text(self, message: Message) -> str:
        return self.localizer.format(message, self.locale)

    def text_or(self, message: Message, fallback: str) -> str:
        """The message's text, or `fallback` when no catalogue has it: an optional message (a field's help) is
        not missing."""
        return self.text(message) if self.localizer.knows(message.id) else fallback

    def summary(self, message: Message) -> tuple[Message, str]:
        """A journal summary and its text; an event no catalogue describes shows its type."""
        text = self.text(message)
        if text != message.id:
            return message, text
        other = Message.of("journal-other", type=str(message.args.get("type", message.id)))
        return other, self.text(other)

    def capability(self, name: str) -> str:
        return self.text_or(capability_message(name), name)
