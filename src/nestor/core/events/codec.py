"""JSON conversion of event payloads, driven by type annotations.

Supported field types: `str`, `int`, `float`, `bool`, `None`, enums, `datetime`, `NewType`s of
those, `X | None`, `tuple[X, ...]`, `Mapping[str, ...]` (kept as plain JSON) and frozen
dataclasses made of supported types. Anything else is a contract error: payloads must stay
plain data so that the event log remains readable without the code that wrote it.
"""

import dataclasses
import enum
import types
import typing
from collections.abc import Mapping
from datetime import datetime
from typing import Any, get_args, get_origin, get_type_hints

from nestor.core.exceptions import ContractError

type JSON = bool | int | float | str | list[JSON] | dict[str, JSON] | None


def encode(value: object) -> JSON:
    if isinstance(value, enum.Enum):  # before str: a StrEnum is also a str
        return encode(value.value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [encode(v) for v in value]
    raise ContractError(f"cannot encode {type(value).__name__} in an event payload")


def decode(value: JSON, hint: Any) -> Any:
    while hasattr(hint, "__supertype__"):  # NewType
        hint = hint.__supertype__
    origin, args = get_origin(hint), get_args(hint)
    if origin in (typing.Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        return decode(value, next(a for a in args if a is not type(None)))
    if hint is Any or hint is object:
        return value
    if origin is tuple and isinstance(value, list):
        return tuple(decode(v, args[0]) for v in value)
    if origin in (dict, Mapping) and isinstance(value, dict):
        return dict(value)
    if isinstance(hint, type):
        if issubclass(hint, enum.Enum):
            try:
                return hint(value)
            except ValueError as error:
                raise ContractError(str(error)) from None
        if hint is datetime and isinstance(value, str):
            return datetime.fromisoformat(value)
        if dataclasses.is_dataclass(hint) and isinstance(value, dict):
            hints = get_type_hints(hint)
            return hint(**{k: decode(v, hints[k]) for k, v in value.items()})
        if hint is float and isinstance(value, int | float):
            return float(value)
        if hint in (str, int, bool) and isinstance(value, hint):
            return value
    raise ContractError(f"cannot decode {value!r} as {hint!r}")
