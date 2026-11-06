"""API v1: what the web front and the local command line call, under `/api/v1`.

Errors are `{"error": {"code", "message"}}`; signed-in requests use the session cookie, and unsafe ones
the `X-CSRF-Token` header (see `security`). `app` assembles it; each resource is a package:

- `routes.py`: the handlers alone, thin (dependencies, a call to the domain, `XOut.of`);
- `schemas.py`: what it takes and sends, each `XOut` built from the domain by its `of`;
- a module named for what it reads or decides, when it has one (`journal/feed.py`, `tasks/afterwards.py`).

What several resources share is in `shared.py` (shapes) and `access.py` (who may reach what); no resource
imports another.
"""
