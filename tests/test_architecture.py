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
import re
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
    "runtime": {"pydantic", "yaml", "ruamel"},  # the configuration, validated and edited round-trip; never in modules
    "admin": {"fastapi", "starlette", "pydantic", "uvicorn"},  # the JSON API served next to Nestor
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


# What people read is in `locales/*.ftl`, rendered by a `Localizer`: never a sentence in Python (test
# doubles aside: their data is French on purpose).
SENTENCE_FREE_EXCEPTIONS = ("testing/",)
_FRENCH = re.compile(r"[àâçéèêëîïôûùüÿœæÀÂÇÉÈÊËÎÏÔÛÙÜŸŒ«»]")


def sentences(path: Path) -> list[str]:
    """String literals, docstrings aside, that look like a French sentence (accents and a space)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and " " in node.value.strip()
        and _FRENCH.search(node.value)
    ]


def test_no_sentence_for_people_is_written_in_python() -> None:
    found = {
        str(p.relative_to(SRC)): s
        for p in PACKAGE.rglob("*.py")
        if not str(p.relative_to(PACKAGE)).startswith(SENTENCE_FREE_EXCEPTIONS) and (s := sentences(p))
    }
    assert not found, found


def test_the_sentence_guard_catches_one(tmp_path: Path) -> None:
    leaky = tmp_path / "leaky.py"
    leaky.write_text('"""Docstrings may quote « un exemple »."""\nAPOLOGY = "Désolé, ça n\'a pas marché."\n')
    assert sentences(leaky) == ["Désolé, ça n'a pas marché."]


def used_message_ids(path: Path) -> set[str]:
    """Ids named in code: `Message.of("id")`, `Message("id", …)`, and API error codes (`error-<code>`)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = ast.unparse(node.func)
        literals = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if name in ("Message.of", "Message") and isinstance(node.args[0], ast.Constant) and literals:
            found.add(literals[0])
        elif (name == "ApiError" and len(literals) == 1) or (name == "not_found" and literals):
            found.add(f"error-{literals[0].replace('_', '-')}")
    return found


def test_every_message_the_code_names_is_in_the_catalogue() -> None:
    catalogue = "\n".join(f.read_text() for f in (PACKAGE / "locales" / "en").glob("*.ftl"))
    defined = {line.split(" =")[0] for line in catalogue.splitlines() if " =" in line and not line.startswith(" ")}
    shipped = [p for p in PACKAGE.rglob("*.py") if not str(p.relative_to(PACKAGE)).startswith("testing/")]
    used = set().union(*(used_message_ids(p) for p in shipped))
    assert used, "the scan finds the messages"
    assert not used - defined, sorted(used - defined)
