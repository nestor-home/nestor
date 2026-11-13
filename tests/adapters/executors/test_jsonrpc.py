"""The JSON-RPC session over a child process: what its end, its noise and its stubbornness do to callers."""

import asyncio
import contextlib
import sys

import pytest

from nestor.adapters.executors.jsonrpc import Closed, Message, RpcError, StdioRpc
from nestor.adapters.executors.process import LINE_LIMIT

ECHO = """
import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if message.get("method") == "die":
        print("fatal: token expired", file=sys.stderr, flush=True)
        sys.exit(3)
    if "id" in message and "method" in message:
        print("not json", flush=True)
        print(json.dumps({"method": "ping", "params": {"threadId": "t1", "n": message["id"]}}), flush=True)
        print(json.dumps({"id": message["id"], "result": message["params"]}), flush=True)
"""


async def refuse(method: str, params: Message) -> Message:
    raise RpcError(-32601, method)


def child(code: str) -> list[str]:
    return [sys.executable, "-c", code]


async def test_a_call_gets_its_result_and_notifications_reach_who_listens_for_their_thread() -> None:
    rpc = StdioRpc(child(ECHO), refuse)
    await rpc.open()
    events = rpc.listen("t1")
    try:
        assert await rpc.call("echo", {"a": 1}, timeout_s=5) == {"a": 1}, "a line that is not JSON is skipped"
        assert (await events.get()) == {"method": "ping", "params": {"threadId": "t1", "n": 1}}
    finally:
        await rpc.close()


async def test_when_the_process_ends_callers_and_listeners_learn_it_with_what_it_last_said() -> None:
    rpc = StdioRpc(child(ECHO), refuse)
    await rpc.open()
    early = rpc.listen("t1")
    with pytest.raises(Closed, match="fatal: token expired"):
        await rpc.call("die", {}, timeout_s=5)
    assert await asyncio.wait_for(early.get(), 5) is None
    assert await asyncio.wait_for(rpc.listen("t2").get(), 5) is None, "a listener that comes after the end too"
    assert not rpc.alive
    with pytest.raises(Closed):
        await rpc.call("echo", {}, timeout_s=5)
    await rpc.close()


async def test_a_command_that_cannot_start_is_closed() -> None:
    with pytest.raises(Closed, match="could not start"):
        await StdioRpc(["codex-that-is-not-installed"], refuse).open()


async def test_a_line_longer_than_the_limit_is_skipped_and_the_session_goes_on() -> None:
    huge = f"import sys; sys.stdout.write('x' * {LINE_LIMIT + 1} + chr(10)); sys.stdout.flush()"
    rpc = StdioRpc(child(f"{huge}\n{ECHO}"), refuse)
    await rpc.open()
    try:
        assert await rpc.call("echo", {"a": 1}, timeout_s=10) == {"a": 1}
    finally:
        await rpc.close()


async def test_a_process_that_closed_its_input_fails_the_call() -> None:
    rpc = StdioRpc(child("import os, time; os.close(0); time.sleep(30)"), refuse)
    await rpc.open()
    try:
        with pytest.raises(Closed):
            for _ in range(50):  # the pipe breaks on a write: the first ones may still be buffered
                with contextlib.suppress(TimeoutError):
                    await rpc.call("echo", {"padding": "x" * 65536}, timeout_s=0.05)
    finally:
        await rpc.close()


async def test_closing_stops_a_process_that_ignores_the_request_to_stop() -> None:
    stubborn = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('{}', flush=True)"
    rpc = StdioRpc(child(f"{stubborn}; time.sleep(60)"), refuse)
    await rpc.open()
    await asyncio.sleep(0.3)
    async with asyncio.timeout(15):
        await rpc.close()
    assert not rpc.alive
