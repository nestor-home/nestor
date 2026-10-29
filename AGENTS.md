# AGENTS.md

Nestor is an open-source framework for intelligent home assistants. This file is for coding agents:
read it before changing anything.

## Commands

```bash
uv sync                      # installs the dev group by default
uv run pre-commit install    # once: ruff, ty and lockfile checks on every commit
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
```

All four must pass before a change is done; CI runs them on Python 3.12 to 3.14 with `uv sync --locked`.
Manage dependencies with `uv add` / `uv remove` only, and commit `uv.lock`.

## Architecture rules

1. **The core never depends on a vendor.** Third-party SDKs (STT, TTS, LLM, robots, Home Assistant
   clients…) are imported only inside `nestor.adapters.<name>`. `tests/test_architecture.py` enforces it;
   adding a package to its `CORE_ALLOWED` list is a design decision, not a fix.
2. **Contract first.** Define or evolve the port (typed protocol, events) before writing an adapter.
3. **Minimum hardware is a CPU, a microphone and a speaker.** Robots, cameras, screens are optional
   capabilities: their absence disables a feature, never breaks the assistant.
4. **The central agent stays fast.** Nothing slow sits in the conversation loop; long work is
   delegated to an `Executor`, frequent short actions are direct tools.
5. **The event log is the source of truth.** Every observable effect (turn, tool call, task, memory
   change, proactive speech, policy decision) is written to it.
6. **Integrate, don't reimplement.** Home Assistant for the home, MCP for third-party tools,
   external agents for long tasks.
7. **Measure before adopting.** Providers, models and tuning are chosen on reproducible benchmarks;
   untested capabilities are labelled as such.

## Tests

- Test behaviour, not implementation: never assert what the code merely restates.
- Cover at least the happy path, a provider outage, a cancellation and a missing optional capability.
- Hardware and network paths have fake adapters; real-provider tests are marked `live` and opt-in.

## Conventions

- Python 3.12+, fully typed and checked with `ty`; `ruff` for linting and formatting, line length 120.
- Async I/O with explicit timeouts and cancellation; close every resource.
- No secrets in the repository; configuration is validated, secrets come from the environment.
- Keep the repository lean: no new Markdown files unless they are needed by users or agents.
