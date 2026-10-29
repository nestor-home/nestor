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

## License

[MIT](LICENSE)
