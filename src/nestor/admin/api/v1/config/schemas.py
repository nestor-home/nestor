"""The configuration as the admin edits it: its schema with each property's words, the document, the changes a
write makes, its history and its secrets."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from nestor.admin.api.v1.errors import ProblemOut
from nestor.admin.api.v1.shared import Input
from nestor.admin.presentation import Phrasebook
from nestor.core import ModelType
from nestor.core.i18n import Message
from nestor.runtime.editing import ConfigSchema, Diff, Shape, Suggest
from nestor.runtime.secrets import ConfigSecrets, preview


def _humanize(name: str) -> str:
    return name.replace("_", " ").capitalize()


def _render(node: Any, words: Phrasebook) -> Any:
    """Fills `x-nestor.title` and `help` in the reader's language: the field's own message, else the
    generic one for that field name, else its name."""
    if isinstance(node, dict):
        meta = node.get("x-nestor")
        if isinstance(meta, dict):
            generic = words.text_or(Message(meta["fallback_title_id"]), _humanize(meta["field"]))
            meta["title"] = words.text_or(Message(meta["title_id"]), generic)
            help_text = words.text_or(Message(meta["help_id"]), "")
            meta["help"] = help_text or None
        for child in node.values():
            _render(child, words)
    elif isinstance(node, list):
        for child in node:
            _render(child, words)
    return node


class SlotOut(BaseModel):
    family: str  # the plugin family the slot takes (`channel`)
    shape: Shape  # one component, a list, or components under names other keys use
    required: bool
    title: str
    picks: list[str]  # the keys of an entry that pick its plugin: `kind`, or a model's `provider` and `type`
    kinds: dict[str, dict[str, Any]]  # JSON Schema of each installed plugin's settings, by plugin id (picks' values)
    model_types: dict[str, ModelType]  # what each plugin of the model slot serves (empty elsewhere)


class ConfigSchemaOut(BaseModel):
    sections: dict[str, dict[str, Any]]  # persona, household (one person), agent, watches, initiative, admin, data_dir
    section_titles: dict[str, str]
    slots: dict[str, SlotOut]  # models, channels, executors, tools, inbound, home, connectors
    suggestions: list[Suggest]  # what a field's `x-nestor.suggest_keys` and `suggest_values` may name

    @classmethod
    def of(cls, schema: ConfigSchema, words: Phrasebook) -> "ConfigSchemaOut":
        slots = {
            key: SlotOut(
                family=slot["family"],
                shape=slot["shape"],
                required=slot["required"],
                picks=slot["picks"],
                title=words.text_or(Message(f"config-slot-{key}"), _humanize(key)),
                kinds=_render(slot["kinds"], words),
                model_types=slot["model_types"],
            )
            for key, slot in schema.slots().items()
        }
        sections = _render(schema.sections(), words)
        titles = {name: words.text_or(Message(f"config-section-{name}"), _humanize(name)) for name in sections}
        return cls(sections=sections, section_titles=titles, slots=slots, suggestions=list(Suggest))


class ConfigOut(BaseModel):
    document: dict[str, Any]  # as written: `${VAR}` and `${secret:name}` stay references, literal secrets masked
    path: str  # the file
    restart_required: bool
    pending_changes: list[str]  # paths written since the instance started


class DocumentIn(Input):
    document: dict[str, Any]


class ChangeOut(BaseModel):
    path: str
    before: Any = None  # None for a secret: only that it changed is said
    after: Any = None
    secret: bool = False


class DiffOut(BaseModel):
    added: list[ChangeOut]
    removed: list[ChangeOut]
    changed: list[ChangeOut]

    @classmethod
    def of(cls, diff: Diff) -> "DiffOut":
        def out(changes: list[Any]) -> list[ChangeOut]:
            return [ChangeOut(path=c.path, before=c.before, after=c.after, secret=c.secret) for c in changes]

        return cls(added=out(diff.added), removed=out(diff.removed), changed=out(diff.changed))


class PreviewOut(BaseModel):
    valid: bool
    problems: list[ProblemOut]
    diff: DiffOut


class WrittenOut(BaseModel):
    diff: DiffOut
    restart_required: bool  # always true after a write: a person restarts when ready
    pending_changes: list[str]


class HistoryEntryOut(BaseModel):
    id: str
    at: datetime
    size: int


class HistoryDocumentOut(BaseModel):
    id: str
    at: datetime
    document: dict[str, Any]


class SecretOut(BaseModel):
    name: str
    set: bool
    preview: str | None  # enough to recognise it, never enough to use it
    used_by: list[str]  # the configuration's paths that refer to it

    @classmethod
    async def of(cls, name: str, secrets: ConfigSecrets, used: dict[str, list[str]]) -> "SecretOut":
        """`used`: the configuration's paths referring to each secret."""
        value = await secrets.value(name)
        return cls(
            name=name, set=value is not None, preview=preview(value) if value else None, used_by=used.get(name, [])
        )


class SecretIn(Input):
    value: str = Field(min_length=1)
