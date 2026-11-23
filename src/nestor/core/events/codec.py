"""JSON conversion of event payloads, driven by type annotations.

Supported field types: `str`, `int`, `float`, `bool`, `None`, enums, `datetime`, `time`, `NewType`s of
those, `X | None`, `tuple[X, ...]`, `Mapping[K, V]` (its keys and values decoded as `K` and `V`: an enum's keys come
back as its members, `object` values as plain JSON) and frozen
dataclasses made of supported types. Anything else is a contract error: payloads must stay
plain data so that the event log remains readable without the code that wrote it.
"""

import dataclasses
import enum
import types
import typing
from collections.abc import Mapping
from datetime import datetime, time
from typing import Any, get_args, get_origin, get_type_hints

from nestor.core.exceptions import ContractError

type JSON = bool | int | float | str | list[JSON] | dict[str, JSON] | None


def encode(value: object) -> JSON:
    if isinstance(value, enum.Enum):  # before str: a StrEnum is also a str
        return encode(value.value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime | time):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return [encode(v) for v in value]
    raise ContractError(f"cannot encode {type(value).__name__} in an event payload")


def decode(value: JSON, hint: Any) -> Any:
    while hasattr(hint, "__supertype__") or isinstance(hint, typing.TypeAliasType):  # NewType, `type X = …`
        hint = hint.__supertype__ if hasattr(hint, "__supertype__") else hint.__value__
    origin, args = get_origin(hint), get_args(hint)
    if origin in (typing.Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        members = [a for a in args if a is not type(None)]
        for member in members[:-1]:  # the first member the value reads as
            try:
                return decode(value, member)
            except ContractError:
                continue
        return decode(value, members[-1])
    if hint is Any or hint is object:
        return value
    if origin is tuple and isinstance(value, list):
        return tuple(decode(v, args[0]) for v in value)
    if origin in (dict, Mapping) and isinstance(value, dict):
        key, item = args or (str, object)
        return {decode(k, key): decode(v, item) for k, v in value.items()}
    if isinstance(hint, type):
        if issubclass(hint, enum.Enum):
            try:
                return hint(value)
            except ValueError as error:
                raise ContractError(str(error)) from None
        if hint is datetime and isinstance(value, str):
            return datetime.fromisoformat(value)
        if hint is time and isinstance(value, str):
            return time.fromisoformat(value)
        if dataclasses.is_dataclass(hint) and isinstance(value, dict):
            hints = get_type_hints(hint)
            return hint(**{k: decode(v, hints[k]) for k, v in value.items()})
        if hint is float and isinstance(value, int | float):
            return float(value)
        if hint in (str, int, bool) and isinstance(value, hint):
            return value
    raise ContractError(f"cannot decode {value!r} as {hint!r}")
