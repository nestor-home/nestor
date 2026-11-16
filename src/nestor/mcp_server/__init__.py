"""Nestor's MCP server for executors, on the admin's address at `/mcp`: what an executor reaches while it works on a
task (its brief, the requester's memory, questions to them, its progress, its files).

Every call carries the executor's key (`Authorization: Bearer nstx_…`) and the task's capability (`task`, `nstt_…`):
the key says who calls, the capability what for. A tool runs only when both match a task of that executor that is
still running; otherwise every refusal reads the same. Calls are limited per key, and each is journaled
(`ExecutorCalled`); what a tool does is journaled by its module, as when the agent does it.

- `server.py`: the MCP server and the endpoint the admin serves, assembled from the tools;
- `guard.py`: the key and the rate, checked before the MCP app sees a request;
- `access.py`: what every tool builds on (its task, its requester, when its conversation started);
- `links.py` and `files.py`: short-lived links to the tasks' files, and the endpoint behind them (`/mcp/files/…`):
  files never go through the executor's model;
- `tools/`: the tools, a module per subject, each with a `register(mcp, access)`; a new subject is a new module
  listed in `tools/__init__.py`.
"""

from nestor.mcp_server.server import FILES, ExecutorServer

__all__ = ["FILES", "ExecutorServer"]
