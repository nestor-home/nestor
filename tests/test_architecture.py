"""Architecture rules that must hold as the codebase grows.

Layers, from the most stable to the most specific:
    core      → standard library only
    modules   → core
    runtime   → core, modules, adapters (it assembles them)
    admin     → core, modules, runtime (the web interface over an assembled Nestor)
    testing   → core, modules (the test kit ships with the package: no third-party imports)
    adapters  → anything: each adapter owns its vendor SDK
"""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
PACKAGE = SRC / "nestor"
ALLOWED_INTERNAL = {
    "core": {"core"},
    "modules": {"core", "modules"},
    "runtime": {"core", "modules", "runtime", "adapters"},  # composes the built-in storage
    "testing": {"core", "modules", "testing"},
    "admin": {"core", "modules", "runtime", "admin"},  # the web interface over an assembled Nestor
}
# Third-party packages allowed outside adapters, per layer. Each addition is a design decision.
THIRD_PARTY_ALLOWED: dict[str, set[str]] = {
    "runtime": {"pydantic", "yaml"},  # validated configuration; never seen by modules
    "admin": {"fastapi", "starlette", "jinja2", "uvicorn"},  # server-rendered pages served next to Nestor
}


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def violations(path: Path, package: Path = PACKAGE) -> list[str]:
    layer = path.relative_to(package).parts[0]
    if layer not in ALLOWED_INTERNAL:  # adapters, package root
        return []
    wrong = []
    for name in imports(path):
        parts = name.split(".")
        if parts[0] == "nestor":
            if len(parts) > 1 and parts[1] not in ALLOWED_INTERNAL[layer]:
                wrong.append(f"{name} (layer {layer!r} may not depend on {parts[1]!r})")
        elif parts[0] not in sys.stdlib_module_names and parts[0] not in THIRD_PARTY_ALLOWED.get(layer, set()):
            wrong.append(f"{name} (third-party import outside nestor.adapters)")
    return wrong


def test_layers_only_depend_on_more_stable_layers() -> None:
    found = {str(p.relative_to(SRC)): v for p in PACKAGE.rglob("*.py") if (v := violations(p))}
    assert not found, found


@pytest.mark.parametrize(
    ("layer", "source", "expected"),
    [
        ("core", "from nestor.modules.cognition import Executor", "may not depend on 'modules'"),
        ("modules", "import elevenlabs", "third-party import"),
        ("testing", "from pipecat.frames import Frame", "third-party import"),
    ],
)
def test_the_guard_catches_a_forbidden_import(tmp_path: Path, layer: str, source: str, expected: str) -> None:
    fake = tmp_path / "nestor" / layer / "leaky.py"
    fake.parent.mkdir(parents=True)
    fake.write_text(source + "\n")
    assert any(expected in v for v in violations(fake, package=tmp_path / "nestor"))
