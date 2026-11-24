"""Hermes as a remote executor, through its Runs HTTP API (read in `gateway/platforms/api_server_runs.py`).

A turn is a run: started with `POST runs`, followed on `GET runs/{id}/events` (server-sent events), steered with
`POST runs/{id}/steer` (`input`; accepted only while the run is `running`) and stopped with `POST runs/{id}/stop`;
`GET runs/{id}` gives its state. A finished run's state carries its `status`, `output` and `session_id`, and the events
stream of a finished run replays every event up to the terminal one, then closes. Following a run therefore reads its
state first and only streams while it is still going, which also makes `follow` safe to call again after a restart.

A task's turns share a Hermes session: the first run's `session_id` (its run id) is the outcome's `session`, and a
run started with `session_id` loads that session's history. A steer Hermes could not deliver before the run ended
comes back as `pending_steer` on its terminal event: the outcome says it, so it is not lost.

A turn that needs its owner ends on a question in its final report, a JSON object (`report`, `question`) the
instructions ask for, as the coding agents' structured report. Hermes's own `clarify` is not the way: it holds the run
and a worker until the answer, an hour at most by default, when the person may answer days later. A run that asks
with `clarify` anyway is stopped and its turn ends on that question; the answer starts the next turn, in the session.

A session Hermes no longer has cannot be told apart: `POST runs` with an unknown `session_id` is not refused, its run
starts with an empty history under that id (Hermes reads the session's messages and finds none). Such a turn goes on
without the turns before, never as `Outcome.lost`.
"""

from nestor.adapters.executors.hermes.executor import HermesExecutor
from nestor.adapters.executors.hermes.settings import HermesSettings, build
from nestor.runtime import Family, Plugin

__all__ = ["HermesExecutor", "HermesSettings", "build", "plugin"]

plugin = Plugin(Family.EXECUTOR, "hermes", HermesSettings, build)
