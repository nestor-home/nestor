"""Architecture rules that must hold as the codebase grows.

The core never depends on a vendor: third-party packages may only be imported from
`nestor.adapters`, where each adapter owns its SDK.
"""

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "nestor"
ADAPTERS = SRC / "adapters"
# Third-party packages the core may use (validation, typing…). Each addition is a design decision.
CORE_ALLOWED: set[str] = set()


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_core_imports_no_vendor_package():
    offenders = {}
    for path in SRC.rglob("*.py"):
        if ADAPTERS in path.parents:
            continue
        foreign = imported_roots(path) - set(sys.stdlib_module_names) - {"nestor"} - CORE_ALLOWED
        if foreign:
            offenders[str(path.relative_to(SRC))] = sorted(foreign)
    assert not offenders, f"vendor imports outside nestor.adapters: {offenders}"


def test_the_guard_catches_a_vendor_import(tmp_path):
    module = tmp_path / "leaky.py"
    module.write_text("import elevenlabs\nfrom pipecat.frames import Frame\nimport asyncio\n")
    assert imported_roots(module) - set(sys.stdlib_module_names) == {"elevenlabs", "pipecat"}
