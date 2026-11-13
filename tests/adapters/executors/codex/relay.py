"""Relays standard input and output to a TCP port, as `codex app-server proxy` relays them to the Codex daemon's
socket: the fake daemon of the tests lives on while sessions come and go."""

import asyncio
import sys


async def main(port: int) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=2**26)
    stdin = asyncio.StreamReader(limit=2**26)
    loop = asyncio.get_running_loop()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(stdin), sys.stdin)

    async def up() -> None:
        while data := await stdin.read(65536):
            writer.write(data)
            await writer.drain()

    async def down() -> None:
        while data := await reader.read(65536):
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()

    tasks = [asyncio.create_task(up()), asyncio.create_task(down())]
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
