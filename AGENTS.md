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
`pytest` also measures branch coverage and fails under 95 %. Manage dependencies with `uv add` /
`uv remove` only, and commit `uv.lock`.

## Layout

```text
src/nestor/
├── core/                 kernel shared by everything (stdlib only)
│   ├── contracts/        Component lifecycle, capabilities
│   ├── events/           versioned Event base, JSON codec for the log
│   ├── shared/           identifiers, clock
│   └── exceptions.py     error hierarchy
├── modules/              domain modules
│   ├── channels/         entry points (voice, messaging, web) and the assistant they reach
│   ├── conversation/     the central agent (Agent), persona, history rebuilt from the journal
│   ├── cognition/
│   │   ├── model/        the central agent's language model
│   │   ├── tools/        direct tools, the toolbox that runs and logs them
│   │   └── delegation/   executors, durable tasks rebuilt from the journal, delegation tools
│   ├── household/        people and their accounts on channels
│   ├── home/             presence as the home system knows it (device control goes through its MCP server)
│   ├── memory/           memories per person: journaled changes, searchable store, agent tools
│   ├── identity/         diarization and speaker identification ports (opt-in, never authorisation)
│   ├── connectors/       third-party services plugged in from the admin: OAuth, vault, tools, inbound
│   ├── satellites/       pairing, manifests, the `nestor.satellite/1` wire format and its JSON Schemas
│   ├── initiative/       what the agent says unprompted
│   │   ├── delivery/     the courier and its presence-aware policy
│   │   └── watches/      durable watches, inbound sources, triage
│   ├── behavior/         attitude and expressions, translated by the plugged body
│   └── journal/          the append-only event log, live subscriptions, blobs
├── runtime/              composition: configuration, adapter registry, lifecycle
├── admin/                the web admin (connections, supervision) over the assembled Nestor
├── cli.py                the `nestor` command, above runtime and admin
├── adapters/             adapters/<family>/<vendor>/ — the only place for third-party SDKs
│   └── storage/          SQLite (one WAL database, migrations in schema.py), blobs on disk
└── testing/              doubles and contract suites, mirroring modules/ (shipped with the package)
tests/                    mirrors src/nestor
```

Every domain package follows the same template: `types.py` (values and enums), `ports.py` (abstract
contracts adapters implement), `events.py` (what it writes to the log), `service.py` (domain logic,
or a file named after its class when there are several), `assistant.py` (the tools and instruction
section the central agent gets from it), and an `__init__.py` that exposes the public names. Split a
module into sub-packages as soon as it holds more than one concept (`cognition/model`,
`cognition/delegation`, `initiative/delivery`, `initiative/watches`); tests mirror the same tree.

New modules (memory, home, initiative, channels, identity, perception) and the `runtime/` and
`adapters/` packages are created when their first ticket lands, not before.

Layers only depend on more stable ones: `core` ← `modules` ← `runtime` ← `admin`; `testing` sees `core`
and `modules`; adapters may import anything and are the only place for third-party SDKs; the
runtime may assemble the built-in storage adapters, and the admin may use FastAPI and Jinja2.
`tests/test_architecture.py` enforces it.

## Architecture rules

1. **The core never depends on a vendor.** Third-party SDKs are imported only inside
   `nestor.adapters`. Allowing a package elsewhere (`THIRD_PARTY_ALLOWED`) is a design decision.
2. **Contract first.** Define or evolve the port and its contract suite before writing an adapter.
3. **Minimum hardware is a CPU, a microphone and a speaker.** Robots, cameras, screens are optional
   capabilities: their absence disables a feature, never breaks the assistant.
4. **The central agent stays fast.** Nothing slow sits in the conversation loop; long work is
   delegated to an `Executor`, frequent short actions are direct tools.
5. **The event log is the source of truth.** Every observable effect (turn, tool call, task, memory
   change, proactive speech, policy decision) is an `Event`.
6. **Integrate, don't reimplement.** Home Assistant for the home, MCP for third-party tools,
   external agents for long tasks, an existing voice pipeline for realtime audio.
7. **Measure before adopting.** Providers, models and tuning are chosen on reproducible benchmarks;
   untested capabilities are labelled as such.

## Code conventions

- **Ports** are abstract classes deriving from `Component` (name, capabilities, `start`/`close`,
  async context manager). Their docstring states the contract; `nestor.testing` checks it.
- **Values** are frozen dataclasses (`slots=True`, `kw_only=True` when there are many fields);
  closed sets are `StrEnum`s. No dicts of loosely typed data across module boundaries.
- **Events** are declared in the owning module's `events.py`:
  `class TaskStarted(Event, event_type="task.started")`. Payloads are plain data (see
  `nestor.core.codec`); changing one means bumping `version` and migrating older records.
- **Errors** derive from `NestorError`. Adapters translate vendor exceptions into `ProviderError`
  (with `transient` set) — a vendor exception never reaches a module.
- **Async**: explicit timeouts, cancellation honoured, resources released in `close`.
- **Public API**: each module exposes its names in `__init__.py` (`__all__`); import from the module
  (`from nestor.modules.cognition import Executor`), not from its files, outside that module.
- Python 3.12+ syntax (`type` aliases, `X | None`), fully typed and checked with `ty`; `ruff`,
  line length 120. Code, docstrings and identifiers in English.
- No secrets in the repository; secrets come from the environment.
- Keep the repository lean: no new Markdown files unless users or agents need them.

## Tests

- Test behaviour, not implementation: never assert what the code merely restates, never test a
  trivial getter. One behaviour per test, named as a sentence.
- Every port has a **contract suite** in `nestor.testing`; doubles and real adapters run the same
  suite (`class TestHermesExecutor(ExecutorContract)`). A suite proves its worth by rejecting a broken
  double, so each suite has such a test.
- Cover at least the happy path, a provider outage, a cancellation and a missing optional capability.
- Uncovered code is either tested for a real behaviour or deleted — not excluded.
- Hardware and network paths use doubles; real-provider tests are marked `live` and opt-in.
