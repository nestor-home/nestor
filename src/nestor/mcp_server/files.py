"""The endpoint behind `links`, at `/mcp/files/<link>`: GET downloads a file sent with the task, PUT uploads one made
for it (the raw content as the body, at most `FILE_BYTES`). Any link that is not valid, or whose task no longer runs,
reads the same: 404."""

from urllib.parse import quote

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from nestor.mcp_server.access import FILE_BYTES
from nestor.mcp_server.links import Links, Way
from nestor.modules.channels import Attachment, AttachmentKind
from nestor.modules.cognition.delegation import TaskStatus
from nestor.runtime import Nestor

NO_LINK = "no such link"


class FileLinks:
    def __init__(self, nestor: Nestor, links: Links) -> None:
        self._nestor, self._links = nestor, links

    async def endpoint(self, request: Request) -> Response:
        token = request.path_params["token"]
        link = self._links.read(token)
        task = self._nestor.tasks.tasks.get(link.task) if link else None
        if link is None or task is None or task.status is not TaskStatus.RUNNING:
            return PlainTextResponse(NO_LINK, status_code=404)
        if link.way is Way.DOWNLOAD and request.method == "GET":
            data = await self._nestor.blobs.get(link.file)
            name = next((g.name for g in task.given if g.file.digest == link.file), "file")
            disposition = f"attachment; filename*=UTF-8''{quote(name, safe='')}"
            return Response(data, media_type=link.media_type, headers={"content-disposition": disposition})
        if link.way is Way.UPLOAD and request.method == "PUT":
            data = bytearray()
            async for chunk in request.stream():
                data += chunk
                if len(data) > FILE_BYTES:
                    return PlainTextResponse(f"larger than {FILE_BYTES // 1_000_000} MB", status_code=413)
            self._links.used(token)
            made = Attachment(
                kind=AttachmentKind.of(link.media_type), data=bytes(data), media_type=link.media_type, name=link.file
            )
            kept = await self._nestor.tasks.add_file(task, made)
            return JSONResponse({"status": "attached", "file": kept.digest, "bytes": kept.size})
        return PlainTextResponse("download with GET, upload with PUT", status_code=405)
