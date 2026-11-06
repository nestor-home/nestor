"""The journal's live stream as Server-Sent Events: new entries as they are written, and the agent's activity
as it changes."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from nestor.admin.api.v1.agent.schemas import AgentActivityOut
from nestor.admin.api.v1.journal.feed import Feed
from nestor.admin.api.v1.security import Caller
from nestor.admin.state import AdminState
from nestor.modules.accounts import Scope


async def events(admin: AdminState, caller: Caller, feed: Feed, position: int) -> AsyncIterator[str]:
    """From after `position`, until the client leaves, its session ends or the server stops. The journal
    subscription only wakes the loop: entries are read from the log, so none is missed."""
    subscription = admin.nestor.journal.subscribe()
    closing = asyncio.ensure_future(admin.closing.wait())
    monitor = admin.nestor.activity if caller.principal.can(Scope.AGENT_READ) else None
    sent: AgentActivityOut | None = None
    waits: set[asyncio.Future[Any]] = set()
    try:
        yield "retry: 3000\n\n"
        while True:
            changed = asyncio.ensure_future(monitor.changes().wait()) if monitor else None  # before reading it
            if monitor is not None and (activity := AgentActivityOut.of(monitor.current())) != sent:
                sent = activity
                yield f"event: activity\ndata: {json.dumps(activity.model_dump(mode='json'))}\n\n"
            items, position, more = await feed.after(position)
            for item in items:
                yield f"id: {item.position}\nevent: item\ndata: {json.dumps(item.model_dump(mode='json'))}\n\n"
            if more or (not signed_in(admin, caller) or closing.done()):
                if changed:
                    changed.cancel()
                if more:
                    continue
                return
            woken = asyncio.ensure_future(subscription.next())
            waits = {woken, closing} | ({changed} if changed else set())
            done, _ = await asyncio.wait(waits, timeout=admin.settings.heartbeat_s, return_when=asyncio.FIRST_COMPLETED)
            for pending in waits - {closing} - done:
                pending.cancel()
            if not done:
                yield ": heartbeat\n\n"
    finally:
        for pending in waits:
            pending.cancel()
        closing.cancel()
        subscription.close()


def signed_in(admin: AdminState, caller: Caller) -> bool:
    """The caller's session is still open, on an account still enabled."""
    if caller.session is None or not admin.sessions.alive(caller.session):
        return False
    account = admin.accounts.accounts.get(caller.session.account_id or "")
    return account is not None and not account.disabled
