"""Hermes as a remote executor, through its Runs HTTP API.

A run is started with `POST runs`, followed on `GET runs/{id}/events` (server-sent events) and
stopped with `POST runs/{id}/stop`; `GET runs/{id}` gives its state. Observed on a Hermes server
(2026-10-30): a finished run's state carries its `status` and `output`, and the events stream of a
finished run replays every event up to the terminal one, then closes. Following a run therefore
reads its state first and only streams while it is still going, which also makes `follow` safe to
call again after a restart.
"""

from nestor.adapters.executors.hermes.executor import HermesExecutor
from nestor.adapters.executors.hermes.settings import HermesSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["HermesExecutor", "HermesSettings", "build", "plugin"]

plugin = Plugin(Family.EXECUTOR, "hermes", HermesSettings, build)
