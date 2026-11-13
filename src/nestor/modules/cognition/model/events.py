"""What the language models write to the log."""

from nestor.core import Event


class ModelFellBack(Event, event_type="model.fell-back"):
    """`model` failed before saying anything and `fallback` was asked the same instead (the keys of `models`):
    `error` is why, as the provider said it."""

    model: str
    fallback: str
    error: str
    transient: bool
