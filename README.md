# Nestor

**Nestor** is an open-source framework for intelligent home assistants — the household's butler.

It is built around a fast central agent that understands the home and the people living in it,
remembers each of them, drives Home Assistant, delegates long tasks, speaks up on its own when
something matters, and can be reached by voice as well as through messaging apps.

> **Status: design phase.** The architecture is settled and a measured proof of concept exists;
> the framework itself is not usable yet.

## Principles

- **Fast conversation.** About one second from the end of your sentence to the assistant's voice.
  Interruptible, it ignores your "mm-hm", and it says so out loud when a provider fails.
- **Native Home Assistant.** Rooms, devices, presence and to-do lists as first-class context;
  Nestor can also act as a Home Assistant Assist conversation agent.
- **Memory you control.** Per-person profiles; every memory is dated, sourced, viewable and editable.
- **Delegation.** Long tasks go to execution agents (Hermes, Codex…) while the conversation goes on;
  results are announced when they arrive.
- **Initiative.** It can speak first — an important email, a finished task — when someone is home
  and it is the right moment.
- **One assistant, every channel.** Voice, Telegram, WhatsApp, Discord, web: same agent, same memory.
- **Plug anything.** Third-party integrations through MCP; providers and models are swappable adapters.
- **Minimum hardware: a CPU, a microphone and a speaker.** Robots, cameras and screens are optional
  capabilities, with a shared behavior engine and one adapter per body.
- **Auditable.** An append-only event log is the source of truth for the dashboard, audit and replay.
  Local-first storage on SQLite.

Its reference distribution is **Richie**, a Reachy Mini Wireless home robot.

**Documentation:** [nestorhome.dev/docs](https://nestorhome.dev/docs/): installing the server,
pairing satellites, the satellite protocol, its schemas and the SDKs.

## Running

```bash
pip install nestor-home            # text only (Telegram); add voice with 'nestor-home[voice]'
nestor init                        # writes nestor.yaml, its .env (secrets) and the owner account
nestor -c nestor.yaml check        # fill the keys in .env first
nestor -c nestor.yaml run
```

Satellites talk in writing out of the box; their voice is the `voice` extra. Without it, a configuration
that gives satellites a `voice` says which requirement to install. `nestor init` writes that section only
when the extra is installed and you want it.

Every command reads the `.env` next to the configuration at each start: no need to source it. A variable
already set in the environment (the shell, a service manager) wins over the file.

Models are any OpenAI-compatible server. Hosted providers need a key (`MODEL_API_KEY` in the `.env`);
local ones (Ollama `http://localhost:11434/v1`, LM Studio `http://localhost:1234/v1`, vLLM, llama.cpp)
need none: leave it empty and no `Authorization` header is sent.

`models` holds as many as you like, under names you choose; each role refers to one by name. With a
single model, every role uses it:

```yaml
models:
  haiku: {kind: openai-compatible, base_url: https://openrouter.ai/api/v1, api_key: ${MODEL_API_KEY}, model: anthropic/claude-haiku-5.5}
  sonnet: {kind: openai-compatible, base_url: https://openrouter.ai/api/v1, api_key: ${MODEL_API_KEY}, model: anthropic/claude-sonnet-5.5}
agent:
  spoken: haiku     # answers aloud: the voice starts on its first sentence
  written: sonnet   # answers in writing; either one left out takes the other
watches:
  model: haiku      # sorts incoming items; the written model by default
```

An embedding model is declared with the others; its kind says it embeds. With `memory.embedder`, memories are
found by meaning as well as by words (FTS5 and vectors, fused by reciprocal rank); without it, by words only:

```yaml
models:
  te3: {kind: openai-compatible-embeddings, base_url: https://openrouter.ai/api/v1, api_key: ${MODEL_API_KEY}, model: openai/text-embedding-3-small, dimensions: 1536}
memory:
  embedder: te3     # any model you like: Nestor recommends none
```

Vectors live in the instance's SQLite database (sqlite-vec), one table per embedding space (the model served, its
dimension, its prefixes): switching models embeds every memory again at the next start, and the old vectors go.
With a hosted model, memories leave the house to be embedded.

The medium belongs to the turn: a satellite someone types on gets the written model, the same satellite
spoken to gets the spoken one.

Ports: the admin listens on 8470, satellites on 8471 (their link and their voice). Both are configurable
(`admin.port`, the satellites channel's `port`).

## Development

```bash
uv sync
uv run pre-commit install
uv run ruff check && uv run ty check && uv run pytest
```

### Admin (`web/`)

The admin is a React single-page app (Vite, TanStack Router and Query, Tailwind, shadcn/ui on Base UI,
Project Fluent), built into `src/nestor/admin/static/app/` and served by Nestor itself. It needs Node 22
and pnpm.

```bash
cd web
pnpm install
pnpm dev                                   # on the mock API (MSW), typed against web/openapi.json
NESTOR_API=http://localhost:8470 pnpm dev  # against a running Nestor instead of the mocks
pnpm lint && pnpm typecheck && pnpm test && pnpm build
pnpm api:generate                          # regenerate the client after the API changed
pnpm e2e                                   # Playwright on the mocks, light and dark
NESTOR_URL=http://localhost:8470 E2E_LOGIN=… E2E_PASSWORD=… pnpm e2e:live  # on a throwaway instance
```

On the mocks, sign in as `mathis` (owner) or `lea` (admin) with the password `nestor`; satellites
pair with the code `424242`. The visual identity lives in `web/src/styles/tokens.css`, the logo slot
in `web/src/components/wordmark.tsx`, the admin's texts in `web/src/locales/{en,fr}/*.ftl` (the
server's own messages come from `GET /api/v1/i18n/{locale}`). `pnpm lint` also runs the project's
Biome plugins (`web/lint/*.grit`): no native form controls or hand-written ARIA widgets in features,
no Base UI or cmdk imports outside `components/ui`, no presence variants on cmdk attributes, no
boolean `data-*` attributes that render `"false"`.

Copy: a text earns its place only if it tells the person something they need (a consequence, a rule,
the next step, how to fix an error). No description that restates its title, no "here you can…"
intro, and almost no em dashes (a period, a colon, parentheses or a middle dot instead):
`web/src/i18n/catalog.test.ts` fails on all three. The agent speaks in the first person only where
it speaks (its line on the home page, empty states, toasts after what it does); system texts stay
neutral. Its figure is Nestor's character, the
[`@nestor-home/character`](https://github.com/nestor-home/nestor-character) package, shown through
`web/src/components/agent-figure.tsx`.

## Docker

`compose.yaml` runs the published image with everything it keeps in `./data`
([install](https://nestorhome.dev/docs/)). The container starts as root only to give `/data` to its
`nestor` user (uid 1000) when the folder is not already its own, as Docker creates a missing bind
mount owned by root, then runs as that user; started with `--user`, it runs as given.

Nestor reads `data/.env` itself, at every start: after editing it, `docker compose restart` applies it.
Inside the container, `localhost` is the container: a model server running on the host is
`http://host.docker.internal:<port>/v1` (for Ollama, `http://host.docker.internal:11434/v1`), which
`compose.yaml` maps on Linux as Docker Desktop does on macOS and Windows. On Linux, that address is the
host's Docker bridge, not its loopback: the model server must listen there too (Ollama:
`OLLAMA_HOST=0.0.0.0`; llama.cpp: `--host 0.0.0.0`).

## Checking a satellite

`nestor satellites conformance` checks a satellite written in any language against the
`nestor.satellite/1` standard: see [Conformance](https://nestorhome.dev/docs/satellites/conformance/).

## Benchmarks

`nestor bench` measures a part of Nestor on a dataset and compares configurations: which small model sorts
your mail best, whether a new triage algorithm misses fewer parcels, what it costs per thousand items.

```bash
nestor bench list
nestor bench run watch-triage --variant batch-small.yaml --variant per-watch-small.yaml [--repeat 3] [--cases mine.jsonl]
nestor bench run watch-triage --variant batch-small.yaml --replay      # scored again from the recorded replies
nestor bench compare bench-results/watch-triage/<run> bench-results/watch-triage/<run>
nestor bench report bench-results/watch-triage/<run>
```

A variant is a fragment of `nestor.yaml` (a whole one works too), with the suite's knobs under `bench`;
`${NAME}` resolves from the environment and the `.env` next to it:

```yaml
models:
  mistral-small:
    kind: openai-compatible
    base_url: https://openrouter.ai/api/v1
    api_key: ${OPENROUTER_API_KEY}
    model: mistralai/mistral-small-3.2
    extra_body: {stream_options: {include_usage: true}}  # token counts from servers that only send them on request
persona: {language: French}
bench: {name: batch-mistral-small, algorithm: batch}     # watch-triage: batch or per-watch
```

Two suites ship: `watch-triage` (which mails match a watch) and `memory-recall` (which memories reach a
turn's instructions; it calls no model, its knobs are the `memory` settings).

A suite calls the models of the roles it measures (`watches` for watch-triage); with a single model in the
variant, every role takes it. `models: {fake: {kind: watch-triage-fake}}` runs the suite without a network,
on a deterministic word-overlap judge. A run writes `bench-results/<suite>/<started>-<variant>/results.json` (dataset hash, variant with its
secrets masked, the models the provider says answered, Nestor's version and commit, every case's output and
model calls with latency, tokens and cost) and a self-contained `report.html`; model replies are recorded in
`.bench-cache/`, keyed by model, request, repetition and seed. Both folders are relative to where the
command runs and are not meant to be committed.

A suite is a plugin: a `nestor.bench.Suite` declared in the `nestor.benches` entry-point group, with its
JSONL dataset next to its code (`src/nestor/bench/suites/watch_triage/` is the example). It reads the
records into cases, runs one case with the trial's models (so every call is measured and replayable), and
sums the results up into metrics and findings, whose labels are Fluent messages.

## License

[MIT](LICENSE)
