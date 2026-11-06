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
│   ├── satellites/       pairing, additions, manifests, the `nestor.satellite/1` wire format and its JSON Schemas
│   │                     (the standard: https://nestorhome.dev/docs/satellites/protocol/)
│   ├── initiative/       what the agent says unprompted
│   │   ├── delivery/     the courier and its presence-aware policy
│   │   └── watches/      durable watches, inbound sources, triage
│   ├── behavior/         attitude and expressions, translated by the plugged body
│   └── journal/          the append-only event log, live subscriptions, blobs
├── runtime/              composition: configuration, adapter registry, lifecycle
├── admin/                the admin over the assembled Nestor: accounts sign in to a JSON API (`api/v1`) that
│                         the web front of `web/` is built on; it also serves that front once built
├── bench/                `nestor bench`: the engine (cases, variants, runs, replay cache, reports); its
│   └── suites/           suites, one folder each with its dataset (`nestor.benches` entry points)
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

Layers only depend on more stable ones: `core` ← `modules` ← `runtime` ← `admin`, and `bench` beside
the admin; `testing` sees `core` and `modules`; adapters may import anything and are the only place for third-party SDKs; the
runtime may assemble the built-in storage adapters, and the admin may use FastAPI and pydantic.
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
  `nestor.core.codec`); changing one means bumping `version` and overriding `upgrade`, which
  turns a record of the previous version into the new one as it is read.
- **Errors** derive from `NestorError`. Adapters translate vendor exceptions into `ProviderError`
  (with `transient` set) — a vendor exception never reaches a module.
- **Async**: explicit timeouts, cancellation honoured, resources released in `close`.
- **Public API**: each module exposes its names in `__init__.py` (`__all__`); import from the module
  (`from nestor.modules.cognition import Executor`), not from its files, outside that module.
- Python 3.12+ syntax (`type` aliases, `X | None`), fully typed and checked with `ty`; `ruff`,
  line length 120. Code, docstrings and identifiers in English.
- No secrets in the repository; secrets come from the environment.
- Keep the repository lean: no new Markdown files unless users or agents need them.
- **The admin API has one contract.** A closed set in a response or a query is its domain `StrEnum`
  (never a `Literal` or a `str` restating it, never a `cast`), so `web/openapi.json` lists its values.
  The admin reads the client generated from that file (`pnpm api:generate`: `src/api/schema.gen.ts`,
  with each enum's values) and names its schemas in `src/api/types.ts`; no hand-written shape, union
  or list repeats the server, and the mocks keep their state in those types. The API sends values,
  not their labels: the admin ships Nestor's catalogue and labels a value with the server's select
  message (`role-name`, `task-status`, `journal-kind`…), which has a variant for every value. What
  the mock server answers beyond the schema (configuration schemas, the kind of each event type, the
  scopes of each role) is written by `nestor admin mocks` into `web/src/mocks/server/`. Tests check
  that `openapi.json` and those files are current, and CI that the client is. A table the admin keys
  by a server enum is a `Record` over it, so a new value fails the typecheck until the admin handles it.

## Tests

A test earns its place by catching a bug no other test catches. Before writing one, answer:

1. Which observable behaviour or contract does it protect, and which credible regression makes it fail?
2. Why does no existing test prove it? A contract has **one owner**, at its strongest boundary: the real owner
   with fake I/O beats a mocked collaborator. Extend the keeper's table rather than add a sibling test.
3. Does it need an export, a parameter or a hook that only tests use? Then test at the real boundary instead,
   and never add the seam.

Write down how the code could fail before writing the test. Then:

- Prove the test can fail: break the owner once (an inverted condition, a dropped write), see it red, restore it.
  A fix or a regression test that never went red proves nothing.
- Assert what a user or a caller observes. Never a private attribute, a call shape, a storage key, or an expected
  value the code under test computed. Strict outcomes: "allowed" is the success status, not "not 403".
- The name is a promise: a test called "without secrets" checks for the secrets; a contract that names accents
  feeds accents.
- Doubles are not under test. They run a port's contract suite only where they stand in for the real thing, and
  mocks are fed by the real source (the admin's mocks read the server's catalogues and error codes).
- Ports have a **contract suite** in `nestor.testing`; real adapters run it, and each suite rejects a broken
  double.
- Think through the provider outage, the cancellation, the restart and the missing optional capability when
  listing how the code could fail; test those that are contracts, not each one by habit.
- Coverage is measured, and stays above 95 % through real behaviours: uncovered code is tested for a behaviour
  or deleted, never covered by a test written for the line, never excluded.
- Hardware and network paths use doubles; real-provider tests are marked `live` and opt-in.
- An audit marks every test (retain, fix, consolidate into a named keeper, delete with the proof that remains),
  reads the owner before deciding, and breaks the owner to check every fix and merge.
