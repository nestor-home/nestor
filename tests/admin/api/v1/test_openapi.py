"""What the front builds on: the API's OpenAPI document, from which it generates its client, and the answers its
mock server gives as this version would. Both are committed and must match the server."""

import json
from pathlib import Path

from nestor.adapters.i18n import FluentLocalizer, catalogue_dirs
from nestor.admin import mock_answers, openapi_text
from nestor.cli import main
from nestor.runtime import Registry

WEB = Path(__file__).resolve().parents[4] / "web"
COMMITTED = WEB / "openapi.json"
MOCKS = WEB / "src" / "mocks" / "server"


def test_the_committed_document_is_up_to_date() -> None:
    assert COMMITTED.read_text() == openapi_text(), "run `nestor admin openapi` and commit web/openapi.json"


def test_the_mock_server_answers_as_this_version_does() -> None:
    registry = Registry.installed()
    answers = mock_answers(registry, FluentLocalizer(catalogue_dirs(["nestor", *registry.packages()])))
    assert {p.name: p.read_text() for p in MOCKS.iterdir()} == answers, "run `nestor admin mocks` and commit them"


def test_every_operation_has_a_unique_camel_case_id_and_documents_its_errors() -> None:
    document = json.loads(openapi_text())
    operations = [op for path in document["paths"].values() for op in path.values()]
    ids = [op["operationId"] for op in operations]
    assert len(ids) == len(set(ids))
    assert all(i[0].islower() and "_" not in i for i in ids)
    assert {"createSession", "getMe", "listJournal", "streamJournal", "approveSatellite"} <= set(ids)
    assert all("403" in op["responses"] for op in operations)
    stream = document["paths"]["/api/v1/journal/stream"]["get"]["responses"]["200"]["content"]
    assert "text/event-stream" in stream
    assert all(path.startswith("/api/v1/") for path in document["paths"])


def test_the_command_line_writes_the_document(tmp_path: Path, capsys: object) -> None:
    out = tmp_path / "web" / "openapi.json"
    assert main(["admin", "openapi", "--out", str(out)]) == 0
    assert out.read_text() == openapi_text()
