"""Editing the configuration file from the admin: its schema, the document, its secrets, its history.

The file the command line reads stays the only truth; nothing is applied until a person restarts the
instance (`POST /system/restart`). Forms are built from `GET /config/schema`: every property carries
`x-nestor` — `title` and `help` rendered in the reader's language (with their message ids), whether it
is `advanced`, its `group`, and how it holds secrets:

- `secret`: the value is one (a `SecretStr`, optional or not). The document shows a literal one as
  `{"set": true, "preview": "sk-…4f2"}` and a reference as written (`${secret:name}`); send back that
  echo, `{}` or `{"value": ""}` to keep it, `{"value": "…"}` or plain text to replace it (it goes to the
  vault, the file gets a reference), a reference to point elsewhere, or leave the key out to remove it.
- `secret_values`: the property is a map (`additionalProperties`) whose every value is such a secret
  (HTTP headers). The document shows `{"Authorization": {"set": true, "preview": "Bea…001"}}`; each key
  is kept, replaced or removed on its own, the same way, and a new key comes as `{"value": "…"}`. A
  typed value is kept in the vault as `<slot>.<name>.<field>.<key>`.

A property whose `x-nestor.reference` is a slot (`models`) holds the name of one of that slot's
components: the form offers the names the document gives them.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from nestor.admin.api.v1.config.schemas import (
    ConfigOut,
    ConfigSchemaOut,
    DiffOut,
    DocumentIn,
    HistoryDocumentOut,
    HistoryEntryOut,
    PreviewOut,
    SecretIn,
    SecretOut,
    WrittenOut,
)
from nestor.admin.api.v1.config.writing import write
from nestor.admin.api.v1.errors import ApiError, ProblemOut, not_found
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import state
from nestor.modules.accounts import Scope
from nestor.runtime.editing import ConfigEditor
from nestor.runtime.secrets import ConfigSecrets

router = APIRouter(tags=["config"])
Manager = Annotated[Caller, Depends(allowed(Scope.CONFIG_MANAGE))]


def editor_of(request: Request) -> ConfigEditor:
    """The editor of the file this instance was started from, else 404."""
    editor = state(request).editor
    if editor is None:
        raise ApiError(404, "config_unavailable")
    return editor


def secrets_of(request: Request) -> ConfigSecrets:
    """The vault's secrets, else 409 without a secret key to open it."""
    secrets = state(request).secrets
    if secrets is None:
        raise ApiError(409, "no_secret_key")
    return secrets


def used_secrets(request: Request) -> dict[str, list[str]]:
    """The configuration's paths that refer to each secret (none without an editor)."""
    editor = state(request).editor
    return editor.used_secrets() if editor else {}


Editor = Annotated[ConfigEditor, Depends(editor_of)]
Secrets = Annotated[ConfigSecrets, Depends(secrets_of)]
Used = Annotated[dict[str, list[str]], Depends(used_secrets)]


@router.get("/config/schema")
async def get_config_schema(caller: Manager, editor: Editor) -> ConfigSchemaOut:
    """JSON Schemas of every section and of every installed plugin's settings, with `x-nestor` on each
    property (see the module documentation)."""
    return ConfigSchemaOut.of(editor.schema, caller.phrasebook)


@router.get("/config")
async def get_config(request: Request, caller: Manager, editor: Editor) -> ConfigOut:
    admin = state(request)
    return ConfigOut(
        document=editor.masked(),
        path=str(editor.path),
        restart_required=bool(admin.pending_changes),
        pending_changes=admin.pending_changes,
    )


@router.post("/config/preview")
async def preview_config(caller: Manager, editor: Editor, body: DocumentIn) -> PreviewOut:
    """What writing this document would do: its problems (located), else the changes."""
    outcome = await editor.preview(body.document)
    problems = [ProblemOut.of(p, caller.phrasebook) for p in outcome.problems]
    return PreviewOut(valid=not problems, problems=problems, diff=DiffOut.of(outcome.diff))


@router.put("/config")
async def write_config(request: Request, caller: Manager, editor: Editor, body: DocumentIn) -> WrittenOut:
    """Validate, then write the file (the previous one goes to the history). 422 `config_invalid` with
    `problems` when it cannot be used: nothing is written then. A restart applies it."""
    return await write(state(request), editor, caller, body.document)


@router.get("/config/history")
async def list_config_history(caller: Manager, editor: Editor) -> list[HistoryEntryOut]:
    return [HistoryEntryOut(id=e.id, at=e.at, size=e.size) for e in editor.history()]


@router.get("/config/history/{entry_id}")
async def get_config_history_entry(caller: Manager, editor: Editor, entry_id: str) -> HistoryDocumentOut:
    entry = next((e for e in editor.history() if e.id == entry_id), None)
    document = editor.old(entry_id)
    if entry is None or document is None:
        raise not_found("config_history_unknown")
    return HistoryDocumentOut(id=entry.id, at=entry.at, document=editor.masked(document))


@router.post("/config/history/{entry_id}/restore")
async def restore_config(request: Request, caller: Manager, editor: Editor, entry_id: str) -> WrittenOut:
    """Write an earlier file again — validated like any write, and kept in the history itself."""
    document = editor.old(entry_id)
    if document is None:
        raise not_found("config_history_unknown")
    return await write(state(request), editor, caller, editor.masked(document), restored=entry_id)


@router.get("/config/secrets")
async def list_secrets(caller: Manager, secrets: Secrets, used: Used) -> list[SecretOut]:
    """Every secret set, and every one the configuration refers to (set or not)."""
    names = sorted({*await secrets.names(), *used})
    return [await SecretOut.of(name, secrets, used) for name in names]


@router.get("/config/secrets/{name}")
async def get_secret(caller: Manager, secrets: Secrets, used: Used, name: str) -> SecretOut:
    return await SecretOut.of(name, secrets, used)


@router.put("/config/secrets/{name}")
async def set_secret(caller: Manager, secrets: Secrets, used: Used, name: str, body: SecretIn) -> SecretOut:
    """Write-only: the value is never returned, only a preview."""
    await secrets.set(name, body.value, by=caller.account_id or "cli")
    return await SecretOut.of(name, secrets, used)


@router.delete("/config/secrets/{name}", status_code=204)
async def delete_secret(caller: Manager, secrets: Secrets, used: Used, name: str, force: bool = False) -> Response:
    """409 `secret_in_use` while the configuration refers to it, unless `force`."""
    if (paths := used.get(name, [])) and not force:
        raise ApiError(409, "secret_in_use", paths=", ".join(paths))
    if not await secrets.delete(name, by=caller.account_id or "cli"):
        raise not_found("secret_unknown")
    return Response(status_code=204)
