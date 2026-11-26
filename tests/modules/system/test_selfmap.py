"""`about_nestor`: asked what it could do, the agent gets what is plugged in, what is installed but not configured, what
could be added and the section of the documentation that explains the closest, from the built-in plugins' own cards."""

from typing import Any

import pytest

from nestor.modules.channels import Address
from nestor.modules.cognition.tools import ToolContext
from nestor.modules.system.selfmap import AboutNestor, SelfMap
from nestor.runtime.plugins import BUILT_IN, Registry
from nestor.runtime.selfmap import survey
from nestor.testing.system import StaticDocumentation

CONTEXT = ToolContext(address=Address("web", "chat"))
TOOLS = """# Tools

## Web, weather and maps

One line each in `tools`.

## Feeds, pages and webhooks

Watches follow the sources under `inbound`.

```yaml
# a comment, not a heading
inbound:
  - kind: webhook
```

### Signatures

A post is signed with the hook's secret.

## MCP servers

Remote servers connect in the admin.
"""


@pytest.fixture(scope="module")
def nothing_plugged() -> SelfMap:
    return survey(Registry.installed(distribution=BUILT_IN), [])


async def ask(parts: SelfMap, question: str, docs: StaticDocumentation | None = None) -> dict[str, Any]:
    [tool] = AboutNestor(parts, docs).tools()
    answer = await tool.run({"question": question}, CONTEXT)
    assert isinstance(answer, dict)
    return answer


async def test_with_no_executor_a_long_task_names_the_executors_that_could_be_added(nothing_plugged: SelfMap) -> None:
    answer = await ask(nothing_plugged, "hand over a long task")
    assert "- executor: plugged: none; installed: claude-code, codex, hermes" in answer["overview"]
    relevant = answer["relevant"].splitlines()
    for executor in ("claude-code", "codex", "hermes"):
        line = next(line for line in relevant if line.startswith(f"- {executor} "))
        assert "installed, not configured" in line and f"https://nestorhome.dev/docs/executors/#{executor}" in line


async def test_asked_about_webhooks_it_answers_with_the_source_and_its_section_of_the_docs(
    nothing_plugged: SelfMap,
) -> None:
    docs = StaticDocumentation({"tools": TOOLS})
    answer = await ask(nothing_plugged, "be notified by a webhook", docs)
    assert answer["relevant"].startswith("- webhook (inbound; installed, not configured)")
    assert docs.read == ["tools"]
    excerpt = answer["docs"]
    assert excerpt.startswith("From https://nestorhome.dev/docs/tools/#feeds-pages-and-webhooks:\n## Feeds, pages")
    assert "# a comment, not a heading" in excerpt and "### Signatures" in excerpt, "down to the next section"
    assert "MCP servers" not in excerpt and "Web, weather" not in excerpt


async def test_offline_it_answers_from_the_map_and_says_so(nothing_plugged: SelfMap) -> None:
    answer = await ask(nothing_plugged, "be notified by a webhook", StaticDocumentation(offline=True))
    assert answer["relevant"].startswith("- webhook (inbound;")
    assert "could not be read" in answer["docs"]


async def test_a_question_that_matches_nothing_still_gets_the_whole_map(nothing_plugged: SelfMap) -> None:
    docs = StaticDocumentation({"tools": TOOLS})
    answer = await ask(nothing_plugged, "fly to the moon", docs)
    assert "matches" in answer["relevant"] and "- satellite: " in answer["overview"]
    assert docs.read == [], "no page to read"


def test_the_instructions_gain_one_line(nothing_plugged: SelfMap) -> None:
    guidance = AboutNestor(nothing_plugged).guidance()
    assert "about_nestor" in guidance and "\n" not in guidance
