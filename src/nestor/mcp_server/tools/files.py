"""Files, in base64: those sent with the task (`read_file`), and those the executor hands back with its result
(`attach_file`). Encoding and decoding run off the loop: up to 27 MB of text."""

import asyncio
import base64

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from nestor.mcp_server.access import FILE_BYTES, TaskAccess
from nestor.modules.channels import Attachment, AttachmentKind

TOO_LARGE = f"larger than {FILE_BYTES // 1_000_000} MB"


def register(mcp: MCPServer, access: TaskAccess) -> None:
    nestor = access.nestor

    @mcp.tool(description="The content of a file sent with the task, by its `file` from task_brief, base64.")
    async def read_file(task: str, file: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "read_file")
        sent = next((a for a in (await access.sent(found)).files if a.blob.digest == file), None)
        if sent is None:
            raise ToolError(f"no file {file} was sent with this task")
        if sent.blob.size > FILE_BYTES:
            raise ToolError(f"{sent.name or file} is {TOO_LARGE}")
        encoded = await asyncio.to_thread(base64.b64encode, await nestor.blobs.get(file))
        return {"name": sent.name, "media_type": sent.blob.media_type, "base64": encoded.decode()}

    @mcp.tool(description="Hand a file you made back with the task's result (base64, at most 20 MB).")
    async def attach_file(task: str, name: str, media_type: str, content: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "attach_file")
        try:
            data = await asyncio.to_thread(base64.b64decode, content, validate=True)
        except ValueError:
            raise ToolError("content must be base64") from None
        if len(data) > FILE_BYTES:
            raise ToolError(TOO_LARGE)
        made = Attachment(kind=AttachmentKind.of(media_type), data=data, media_type=media_type, name=name)
        kept = await nestor.tasks.add_file(found, made)
        return {"status": "attached", "file": kept.digest}
