"""The API's OpenAPI document: committed for the front, which generates its client from it."""

import json
from pathlib import Path

from nestor.admin import openapi_text
from nestor.cli import main

COMMITTED = Path(__file__).resolve().parents[4] / "web" / "openapi.json"


def test_the_committed_document_is_up_to_date() -> None:
    assert COMMITTED.read_text() == openapi_text(), "run `nestor admin openapi` and commit web/openapi.json"


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
