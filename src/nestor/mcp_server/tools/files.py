"""Files, by short-lived link (`links`), never through the model's context: a link to download a file sent with the
task (`read_file`), a link to upload a file made for it (`attach_file`). An executor that shares a folder with Nestor
(Claude Code, Codex) has the files sent with the task in its folder and hands back what it makes in its report."""

import posixpath

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from nestor.mcp_server.access import FILE_BYTES, TaskAccess
from nestor.mcp_server.links import LINK_S


def register(mcp: MCPServer, access: TaskAccess) -> None:
    @mcp.tool(
        description=(
            "A link to download a file sent with the task, by its `file` from task_brief: an HTTP GET, within minutes."
        )
    )
    async def read_file(task: str, file: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "read_file")
        given = next((g for g in found.given if g.file.digest == file), None)
        if given is None:
            raise ToolError(f"no file {file} was sent with this task")
        return {
            "name": given.name,
            "media_type": given.file.media_type,
            "bytes": given.file.size,
            "url": access.links.download(found.id, file, given.file.media_type),
            "expires_in_s": LINK_S,
        }

    @mcp.tool(
        description=(
            "When you share no folder with Nestor: a link to upload a file you made, which goes with the task's "
            "result: an HTTP PUT of the file's content as the body (curl -T <file> <upload_url>), within minutes, "
            "once, at most 20 MB."
        )
    )
    async def attach_file(task: str, name: str, media_type: str, ctx: Context) -> dict[str, object]:
        found = await access.task(ctx, task, "attach_file")
        plain = posixpath.basename(name.replace("\\", "/")).strip(" .")
        if not plain:
            raise ToolError("name the file, as the requester will see it")
        return {
            "upload_url": access.links.upload(found.id, plain, media_type),
            "method": "PUT",
            "expires_in_s": LINK_S,
            "max_bytes": FILE_BYTES,
        }
