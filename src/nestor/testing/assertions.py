"""Assertion helpers for contract suites, which must not depend on a test framework."""

from collections.abc import Generator
from contextlib import contextmanager


@contextmanager
def raises(expected: type[BaseException]) -> Generator[None]:
    """Fail unless the block raises `expected` (or a subclass)."""
    try:
        yield
    except expected:
        return
    raise AssertionError(f"{expected.__name__} was not raised")
