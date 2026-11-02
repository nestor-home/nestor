"""What stops a benchmark, said to the person running it."""

from nestor.core import NestorError
from nestor.core.i18n import Message


class BenchError(NestorError):
    """A run, a dataset or a results folder cannot be used; `message` says why, in the person's language."""

    def __init__(self, message: Message) -> None:
        super().__init__(message.id)
        self.message = message
