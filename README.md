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
NESTOR_API=http://localhost:8080 pnpm dev  # against a running Nestor instead of the mocks
pnpm lint && pnpm typecheck && pnpm test && pnpm build
pnpm api:generate                          # regenerate the client after the API changed
pnpm e2e                                   # Playwright on the mocks, light and dark
NESTOR_URL=http://localhost:8080 E2E_LOGIN=… E2E_PASSWORD=… pnpm e2e:live  # on a throwaway instance
```

On the mocks, sign in as `mathis` (owner) or `lea` (admin) with the password `nestor`; satellites
pair with the code `424242`. The visual identity lives in `web/src/styles/tokens.css`, the logo slot
in `web/src/components/wordmark.tsx`, the admin's texts in `web/src/locales/{en,fr}/*.ftl` (the
server's own messages come from `GET /api/v1/i18n/{locale}`). `pnpm lint` also runs the project's
Biome plugins (`web/lint/*.grit`): no native form controls or hand-written ARIA widgets in features,
no Base UI or cmdk imports outside `components/ui`, no presence variants on cmdk attributes, no
boolean `data-*` attributes that render `"false"`.

Copy: a text earns its place only if it tells the person something they need (a consequence, a rule,
the next step, how to fix an error); no description that restates its title, no "here you can…"
intro — `web/src/i18n/catalog.test.ts` fails on both. The agent speaks in the first person only where
it speaks (its line on the home page, empty states, toasts after what it does); system texts stay
neutral. Its figure (`web/src/components/agent-figure.tsx`) stands in for the shared character module
(`web/src/character/`) with the same props, until that module lands.

## License

[MIT](LICENSE)
