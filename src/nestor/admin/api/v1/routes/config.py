"""Editing the configuration file from the admin: its schema, the document, its secrets, its history.

The file the command line reads stays the only truth; nothing is applied until a person restarts the
instance (`POST /system/restart`). Forms are built from `GET /config/schema`: every property carries
`x-nestor` — `title` and `help` rendered in the reader's language (with their message ids), whether it
is `secret` (write-only: shown as `{set, preview}`, typed as `{value}`, blank keeps it) or `advanced`,
and its `group`.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from nestor.admin.api.v1.errors import ApiError, not_found
from nestor.admin.api.v1.models import Input, ProblemOut
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import AdminState, state
from nestor.core.i18n import Message
from nestor.modules.accounts import Scope
from nestor.runtime.editing import ConfigEditor, Diff, EditRefused, Problem, dotted
from nestor.runtime.secrets import ConfigSecrets, preview

router = APIRouter(tags=["config"])
Manager = Annotated[Caller, Depends(allowed(Scope.CONFIG_MANAGE))]


class SlotOut(BaseModel):
    family: str  # the plugin family the slot takes (`channel`)
    many: bool  # a list of components, or one
    required: bool
    title: str
    kinds: dict[str, dict[str, Any]]  # JSON Schema of each installed plugin's settings, by kind


class ConfigSchemaOut(BaseModel):
    sections: dict[str, dict[str, Any]]  # persona, household (one person), initiative, admin, data_dir
    section_titles: dict[str, str]
    slots: dict[str, SlotOut]  # model, triage_model, channels, executors, tools, inbound, presence, connectors


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


class SecretIn(Input):
    value: str = Field(min_length=1)


def _editor(admin: AdminState) -> ConfigEditor:
    if admin.editor is None:
        raise ApiError(404, "config_unavailable")
    return admin.editor


def _secrets(admin: AdminState) -> ConfigSecrets:
    if admin.secrets is None:
        raise ApiError(409, "no_secret_key")
    return admin.secrets


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


def _problem(problem: Problem, words: Phrasebook) -> ProblemOut:
    message = Message.of(
        f"config-error-{problem.code.replace('_', '-')}", path=dotted(problem.path), detail=problem.detail
    )
    return ProblemOut(
        path=list(problem.path),
        code=problem.code,
        message_id=message.id,
        args=dict(message.args),
        message=words.text(message),
    )


def _diff(diff: Diff) -> DiffOut:
    def out(changes: list[Any]) -> list[ChangeOut]:
        return [ChangeOut(path=c.path, before=c.before, after=c.after, secret=c.secret) for c in changes]

    return DiffOut(added=out(diff.added), removed=out(diff.removed), changed=out(diff.changed))


async def _write(
    admin: AdminState, caller: Caller, document: dict[str, Any], restored: str | None = None
) -> WrittenOut:
    try:
        diff = await _editor(admin).write(document, by=caller.account_id or "cli", restored=restored)
    except EditRefused as refused:
        problems = [_problem(p, caller.phrasebook).model_dump() for p in refused.problems]
        raise ApiError(422, "config_invalid", problems=problems, count=len(problems)) from None
    admin.pending_changes = sorted({*admin.pending_changes, *diff.paths})
    return WrittenOut(diff=_diff(diff), restart_required=True, pending_changes=admin.pending_changes)


@router.get("/config/schema")
async def get_config_schema(request: Request, caller: Manager) -> ConfigSchemaOut:
    """JSON Schemas of every section and of every installed plugin's settings, with `x-nestor` on each
    property (see the module documentation)."""
    editor = _editor(state(request))
    words = caller.phrasebook
    slots = {
        key: SlotOut(
            family=slot["family"],
            many=slot["many"],
            required=slot["required"],
            title=words.text_or(Message(f"config-slot-{key}"), _humanize(key)),
            kinds=_render(slot["kinds"], words),
        )
        for key, slot in editor.schema.slots().items()
    }
    sections = _render(editor.schema.sections(), words)
    titles = {name: words.text_or(Message(f"config-section-{name}"), _humanize(name)) for name in sections}
    return ConfigSchemaOut(sections=sections, section_titles=titles, slots=slots)


@router.get("/config")
async def get_config(request: Request, caller: Manager) -> ConfigOut:
    admin = state(request)
    editor = _editor(admin)
    return ConfigOut(
        document=editor.masked(),
        path=str(editor.path),
        restart_required=bool(admin.pending_changes),
        pending_changes=admin.pending_changes,
    )


@router.post("/config/preview")
async def preview_config(request: Request, caller: Manager, body: DocumentIn) -> PreviewOut:
    """What writing this document would do: its problems (located), else the changes."""
    outcome = await _editor(state(request)).preview(body.document)
    problems = [_problem(p, caller.phrasebook) for p in outcome.problems]
    return PreviewOut(valid=not problems, problems=problems, diff=_diff(outcome.diff))


@router.put("/config")
async def write_config(request: Request, caller: Manager, body: DocumentIn) -> WrittenOut:
    """Validate, then write the file (the previous one goes to the history). 422 `config_invalid` with
    `problems` when it cannot be used: nothing is written then. A restart applies it."""
    return await _write(state(request), caller, body.document)


@router.get("/config/history")
async def list_config_history(request: Request, caller: Manager) -> list[HistoryEntryOut]:
    return [HistoryEntryOut(id=e.id, at=e.at, size=e.size) for e in _editor(state(request)).history()]


@router.get("/config/history/{entry_id}")
async def get_config_history_entry(request: Request, caller: Manager, entry_id: str) -> HistoryDocumentOut:
    editor = _editor(state(request))
    entry = next((e for e in editor.history() if e.id == entry_id), None)
    document = editor.old(entry_id)
    if entry is None or document is None:
        raise not_found("config_history_unknown")
    return HistoryDocumentOut(id=entry.id, at=entry.at, document=editor.masked(document))


@router.post("/config/history/{entry_id}/restore")
async def restore_config(request: Request, caller: Manager, entry_id: str) -> WrittenOut:
    """Write an earlier file again — validated like any write, and kept in the history itself."""
    admin = state(request)
    editor = _editor(admin)
    document = editor.old(entry_id)
    if document is None:
        raise not_found("config_history_unknown")
    return await _write(admin, caller, editor.masked(document), restored=entry_id)


async def _secret(admin: AdminState, name: str) -> SecretOut:
    secrets = _secrets(admin)
    value = await secrets.value(name)
    used = admin.editor.used_secrets().get(name, []) if admin.editor else []
    return SecretOut(name=name, set=value is not None, preview=preview(value) if value else None, used_by=used)


@router.get("/config/secrets")
async def list_secrets(request: Request, caller: Manager) -> list[SecretOut]:
    """Every secret set, and every one the configuration refers to (set or not)."""
    admin = state(request)
    used = admin.editor.used_secrets() if admin.editor else {}
    names = sorted({*await _secrets(admin).names(), *used})
    return [await _secret(admin, name) for name in names]


@router.get("/config/secrets/{name}")
async def get_secret(request: Request, caller: Manager, name: str) -> SecretOut:
    return await _secret(state(request), name)


@router.put("/config/secrets/{name}")
async def set_secret(request: Request, caller: Manager, name: str, body: SecretIn) -> SecretOut:
    """Write-only: the value is never returned, only a preview."""
    admin = state(request)
    await _secrets(admin).set(name, body.value, by=caller.account_id or "cli")
    return await _secret(admin, name)


@router.delete("/config/secrets/{name}", status_code=204)
async def delete_secret(request: Request, caller: Manager, name: str, force: bool = False) -> Response:
    """409 `secret_in_use` while the configuration refers to it, unless `force`."""
    admin = state(request)
    used = admin.editor.used_secrets().get(name, []) if admin.editor else []
    if used and not force:
        raise ApiError(409, "secret_in_use", paths=", ".join(used))
    if not await _secrets(admin).delete(name, by=caller.account_id or "cli"):
        raise not_found("secret_unknown")
    return Response(status_code=204)
