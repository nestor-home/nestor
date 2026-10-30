"""Editing the configuration file from the admin: the file the command line reads stays the only truth.

- The document is read and written with a round-trip YAML library: comments and order survive, and the
  file can still be edited by hand.
- Forms are generated from the pydantic models: the core sections, and every installed plugin's
  settings by family and kind, so a third-party plugin gets its form for free.
- Secret fields never reach the file: a value typed in a form goes to the vault, the YAML gets
  `${secret:<name>}`; a blank field keeps what is there.
- An edit is validated before it is written (references resolved, models validated, Nestor built
  without starting); every write keeps the previous file in `<data_dir>/config-history/`.
"""

import io
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, SecretStr, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from nestor.core import NestorError, utc_now
from nestor.modules.journal import Journal
from nestor.modules.system import ConfigChanged
from nestor.runtime.config import (
    AdminConfig,
    InitiativeConfig,
    NestorConfig,
    PersonaConfig,
    PersonConfig,
    references,
    substitute,
)
from nestor.runtime.plugins import Family, Registry
from nestor.runtime.secrets import ConfigSecrets, preview

HISTORY = "config-history"
type Path_ = tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class Slot:
    """Where adapters plug into the configuration: a key of the file, a family of plugins."""

    key: str
    family: Family
    many: bool
    required: bool


SLOTS = (
    Slot("model", Family.MODEL, many=False, required=True),
    Slot("triage_model", Family.MODEL, many=False, required=False),
    Slot("channels", Family.CHANNEL, many=True, required=True),
    Slot("executors", Family.EXECUTOR, many=True, required=False),
    Slot("tools", Family.TOOLS, many=True, required=False),
    Slot("inbound", Family.INBOUND, many=True, required=False),
    Slot("presence", Family.PRESENCE, many=False, required=False),
    Slot("connectors", Family.CONNECTOR, many=True, required=False),
)
SECTIONS: Mapping[str, Any] = {
    "persona": PersonaConfig,
    "household": PersonConfig,  # a list of them
    "initiative": InitiativeConfig,
    "admin": AdminConfig,
}


def secret_fields(model: type[BaseModel], prefix: Path_ = ()) -> set[Path_]:
    """The paths of a settings model's `SecretStr` fields, nested models included."""
    found: set[Path_] = set()
    for name, info in model.model_fields.items():
        annotation = info.annotation
        options = getattr(annotation, "__args__", (annotation,))
        if SecretStr in options:
            found.add((*prefix, name))
        for option in options:
            if isinstance(option, type) and issubclass(option, BaseModel):
                found |= secret_fields(option, (*prefix, name))
    return found


def annotate(schema: dict[str, Any], scope: str, advanced: Iterable[str] = ()) -> dict[str, Any]:
    """Adds `x-nestor` to every property: its title and help message ids (`config-<scope>-<field>`,
    `…-help`), whether it is secret (a `SecretStr`), advanced, and its group."""

    def walk(node: Any, group: str) -> None:
        if isinstance(node, dict):
            for name, prop in (node.get("properties") or {}).items():
                if isinstance(prop, dict):
                    prop["x-nestor"] = {
                        "field": name,
                        "title_id": f"config-{group}-{name}",
                        "help_id": f"config-{group}-{name}-help",
                        "fallback_title_id": f"config-field-{name}",
                        "secret": prop.get("format") == "password" or prop.get("writeOnly") is True,
                        "advanced": bool(prop.pop("advanced", False)) or name in advanced,
                        "group": group,
                    }
            for key, child in node.items():
                if key == "$defs" and isinstance(child, dict):
                    for definition, nested in child.items():
                        walk(nested, f"{scope}-{definition.lower()}")
                elif key != "properties" and isinstance(child, dict | list):
                    walk(child, group)
        elif isinstance(node, list):
            for child in node:
                walk(child, group)

    walk(schema, scope)
    return schema


class ConfigSchema:
    """JSON Schemas of the configuration: core sections, and plugins' settings by slot and kind."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def sections(self) -> dict[str, Any]:
        sections = {name: annotate(model.model_json_schema(), name) for name, model in SECTIONS.items()}
        data_dir = NestorConfig.model_json_schema()["properties"]["data_dir"]
        sections["data_dir"] = annotate({"type": "object", "properties": {"data_dir": data_dir}}, "core")
        return sections

    def slots(self) -> dict[str, Any]:
        return {
            slot.key: {
                "family": slot.family.value,
                "many": slot.many,
                "required": slot.required,
                "kinds": {kind: self.kind(slot, kind) for kind in self.registry.kinds(slot.family)},
            }
            for slot in SLOTS
        }

    def kind(self, slot: Slot, kind: str) -> dict[str, Any]:
        schema = self.registry.get(slot.family, kind).settings.model_json_schema()
        schema.setdefault("properties", {})
        schema["properties"] = {
            "kind": {"const": kind, "type": "string"},
            "name": {"type": "string", "description": "the instance's name; the kind by default"},
            **schema["properties"],
        }
        schema["required"] = ["kind", *schema.get("required", [])]
        return annotate(schema, f"{slot.family.value}-{kind}")

    def secrets_of(self, document: Mapping[str, Any]) -> dict[Path_, str]:
        """Every secret field the document sets, with the vault name a typed value is kept under."""
        found: dict[Path_, str] = {}
        for slot, index, entry in entries(document):
            try:
                model = self.registry.get(slot.family, str(entry.get("kind"))).settings
            except NestorError:
                continue
            where: Path_ = (slot.key, index) if slot.many else (slot.key,)
            label = str(entry.get("name") or entry.get("kind")) if slot.many else slot.key
            for path in secret_fields(model):
                if _get(entry, path) is not None:
                    found[(*where, *path)] = ".".join(
                        [*(([slot.key, label]) if slot.many else [label]), *map(str, path)]
                    )
        return found


def entries(document: Mapping[str, Any]) -> list[tuple[Slot, int, Mapping[str, Any]]]:
    found = []
    for slot in SLOTS:
        value = document.get(slot.key)
        items = value if slot.many and isinstance(value, list) else [value] if isinstance(value, dict) else []
        found += [(slot, i, item) for i, item in enumerate(items) if isinstance(item, dict)]
    return found


def _get(node: Any, path: Path_) -> Any:
    for step in path:
        if (isinstance(node, dict) and step in node) or (
            isinstance(node, list) and isinstance(step, int) and 0 <= step < len(node)
        ):
            node = node[step]
        else:
            return None
    return node


def _set(node: Any, path: Path_, value: Any) -> None:
    for step in path[:-1]:
        node = node[step]
    if value is None and isinstance(node, dict):
        node.pop(path[-1], None)
    else:
        node[path[-1]] = value


def dotted(path: Path_) -> str:
    return ".".join(str(p) for p in path)


def plain(node: Any) -> Any:
    """A round-trip YAML node as plain JSON data."""
    if isinstance(node, dict):
        return {str(k): plain(v) for k, v in node.items()}
    if isinstance(node, list):
        return [plain(v) for v in node]
    if isinstance(node, datetime | Path):
        return str(node)
    return node


def merge(old: Any, new: Any) -> Any:
    """`new` laid over `old`, keeping `old`'s comments and order wherever the structure stays."""
    if isinstance(old, CommentedMap) and isinstance(new, dict):
        for key in [k for k in old if k not in new]:
            del old[key]
        for key, value in new.items():
            old[key] = merge(old[key], value) if key in old else value
        return old
    if isinstance(old, CommentedSeq) and isinstance(new, list):
        for index, value in enumerate(new):
            if index < len(old):
                old[index] = merge(old[index], value)
            else:
                old.append(value)
        del old[len(new) :]
        return old
    return new


@dataclass(frozen=True, slots=True)
class Problem:
    """Why an edit cannot be written: where (a path of the document), what (`code`), and the detail."""

    path: Path_
    code: str  # missing, extra, unknown_kind, reference, invalid
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Change:
    path: str
    before: Any = None  # None for a secret: only that it changed is said
    after: Any = None
    secret: bool = False


@dataclass(frozen=True, slots=True)
class Diff:
    added: list[Change] = field(default_factory=list)
    removed: list[Change] = field(default_factory=list)
    changed: list[Change] = field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        return [c.path for c in (*self.added, *self.removed, *self.changed)]


@dataclass(frozen=True, slots=True)
class Outcome:
    problems: list[Problem]
    diff: Diff


class EditRefused(NestorError):
    def __init__(self, problems: list[Problem]) -> None:
        super().__init__("; ".join(f"{dotted(p.path) or '(document)'}: {p.code} {p.detail}" for p in problems))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    id: str
    at: datetime
    size: int


class ConfigEditor:
    """The configuration file of a running instance, edited in place.

    `build` checks a configuration the way the runtime would build it (`Nestor` without starting); the
    caller passes it, so this module needs no runtime assembly of its own.
    """

    def __init__(
        self,
        path: Path,
        *,
        registry: Registry,
        environ: Mapping[str, str],
        data_dir: Path,
        journal: Journal,
        secrets: ConfigSecrets | None,
        build: Callable[[NestorConfig], object],
    ) -> None:
        self.path, self.registry, self.environ, self.data_dir = path, registry, dict(environ), data_dir
        self.journal, self.secrets, self._build = journal, secrets, build
        self.schema = ConfigSchema(registry)
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.width = 4096  # never fold a long line the person wrote on one
        self._yaml.indent(mapping=2, sequence=4, offset=2)  # `  - item`, as `nestor init` writes it

    # -- reading ---------------------------------------------------------------------------------------

    def document(self) -> CommentedMap:
        return self._yaml.load(self.path.read_text())

    def masked(self, document: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """The document for a form: references as written, literal secrets as `{set, preview}`."""
        shown = plain(document if document is not None else self.document())
        for path in self.schema.secrets_of(shown):
            value = _get(shown, path)
            if isinstance(value, str) and "${" not in value:
                _set(shown, path, {"set": True, "preview": preview(value)})
        return shown

    def used_secrets(self, document: Mapping[str, Any] | None = None) -> dict[str, list[str]]:
        """Secret name → the paths of the document that refer to it."""
        used: dict[str, list[str]] = {}
        for path, name, secret in references(plain(document if document is not None else self.document())):
            if secret:
                used.setdefault(name, []).append(dotted(path))
        return used

    # -- checking and writing --------------------------------------------------------------------------------

    async def preview(self, edited: Mapping[str, Any]) -> Outcome:
        document, pending = self._prepared(edited)
        return Outcome(await self._problems(document, pending), self._diff(document, pending))

    async def write(self, edited: Mapping[str, Any], *, by: str, restored: str | None = None) -> Diff:
        document, pending = self._prepared(edited)
        if problems := await self._problems(document, pending):
            raise EditRefused(problems)
        diff = self._diff(document, pending)
        for name, value in pending.items():
            assert self.secrets is not None  # a typed secret is refused without a vault
            await self.secrets.set(name, value, by=by)
        current = self.document()
        self._keep(self.path.read_text())
        merged = merge(current, document)
        buffer = io.StringIO()
        self._yaml.dump(merged, buffer)
        self.path.write_text(buffer.getvalue())
        await self.journal.publish(
            ConfigChanged(source="config", by=by, changed_paths=tuple(diff.paths), restored=restored)
        )
        return diff

    def _prepared(self, edited: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        """The edited document as it would be written (typed secrets replaced by references), and the
        secrets to put in the vault."""
        document = plain(edited)
        current = plain(self.document())
        current_secrets = {name: path for path, name in self.schema.secrets_of(current).items()}
        pending: dict[str, str] = {}
        for path, name in self.schema.secrets_of(document).items():
            value = _get(document, path)
            if isinstance(value, dict):
                typed = value.get("value") if isinstance(value.get("value"), str) else ""
                if typed:
                    pending[name] = typed
                    _set(document, path, f"${{secret:{name}}}")
                else:  # `{set, preview}` echoed back, or a blank field: what is there stays
                    kept = current_secrets.get(name)
                    _set(document, path, _get(current, kept) if kept else None)
            elif isinstance(value, str) and "${" not in value:
                pending[name] = value
                _set(document, path, f"${{secret:{name}}}")
        return document, pending

    async def _problems(self, document: Mapping[str, Any], pending: Mapping[str, str]) -> list[Problem]:
        problems: list[Problem] = []
        values: dict[str, str] = dict(pending)
        for path, name, secret in references(document):
            if not secret:
                if name not in self.environ:
                    problems.append(Problem(path, "reference", name))
                continue
            if name in values:
                continue
            found = await self.secrets.value(name) if self.secrets else None
            if found is None:
                problems.append(Problem(path, "secret", name))
            else:
                values[name] = found
        if problems:
            return problems
        resolved = substitute(document, self.environ, values.get)
        try:
            config = NestorConfig.model_validate(resolved)
        except ValidationError as error:
            return [Problem(tuple(e["loc"]), _code(e["type"]), e["msg"]) for e in error.errors()]
        for slot, index, entry in entries(resolved):
            where: Path_ = (slot.key, index) if slot.many else (slot.key,)
            try:
                plugin = self.registry.get(slot.family, str(entry.get("kind")))
            except NestorError:
                problems.append(Problem((*where, "kind"), "unknown_kind", str(entry.get("kind"))))
                continue
            settings = {k: v for k, v in entry.items() if k not in ("kind", "name")}
            try:
                plugin.settings.model_validate(settings)
            except ValidationError as error:
                problems += [Problem((*where, *e["loc"]), _code(e["type"]), e["msg"]) for e in error.errors()]
        if problems:
            return problems
        try:
            self._build(config)
        except NestorError as error:
            return [Problem((), "invalid", str(error))]
        return []

    def _diff(self, document: Mapping[str, Any], pending: Mapping[str, str]) -> Diff:
        before, after = _flat(plain(self.document())), _flat(dict(document))
        secret = {dotted(p) for p in self.schema.secrets_of(document)} | {
            dotted(p) for p in self.schema.secrets_of(plain(self.document()))
        }
        changed_secrets = {dotted(p) for p, name in self.schema.secrets_of(document).items() if name in pending}
        diff = Diff()
        for path in sorted(after.keys() - before.keys()):
            diff.added.append(Change(path, None, None if path in secret else after[path], secret=path in secret))
        for path in sorted(before.keys() - after.keys()):
            diff.removed.append(Change(path, None if path in secret else before[path], None, secret=path in secret))
        for path in sorted(before.keys() & after.keys()):
            if before[path] != after[path] or path in changed_secrets:
                hidden = path in secret
                diff.changed.append(
                    Change(path, None if hidden else before[path], None if hidden else after[path], hidden)
                )
        return diff

    # -- history ---------------------------------------------------------------------------------------------

    @property
    def history_dir(self) -> Path:
        return self.data_dir / HISTORY

    def _keep(self, text: str) -> None:
        self.history_dir.mkdir(parents=True, exist_ok=True)
        stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
        (self.history_dir / f"{stamp}.yaml").write_text(text)

    def history(self) -> list[HistoryEntry]:
        if not self.history_dir.is_dir():
            return []
        files = sorted(self.history_dir.glob("*.yaml"), reverse=True)
        return [HistoryEntry(f.stem, _stamp(f.stem), f.stat().st_size) for f in files]

    def old(self, entry_id: str) -> CommentedMap | None:
        found = (
            next((f for f in self.history_dir.glob("*.yaml") if f.stem == entry_id), None)
            if (self.history_dir.is_dir())
            else None
        )
        return self._yaml.load(found.read_text()) if found else None


def _flat(node: Any, path: str = "") -> dict[str, Any]:
    if isinstance(node, dict):
        return {
            k: v for key, child in node.items() for k, v in _flat(child, f"{path}.{key}" if path else str(key)).items()
        }
    if isinstance(node, list):
        return {
            k: v for i, child in enumerate(node) for k, v in _flat(child, f"{path}.{i}" if path else str(i)).items()
        }
    return {path: node}


def _stamp(entry_id: str) -> datetime:
    return datetime.strptime(entry_id, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=utc_now().tzinfo)


_CODES = {"missing": "missing", "extra_forbidden": "extra"}


def _code(kind: str) -> str:
    return _CODES.get(kind, "invalid")
