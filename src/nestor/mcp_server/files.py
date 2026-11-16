"""The endpoint behind `links`, at `/mcp/files/<link>`: GET downloads a file sent with the task, PUT uploads one made
for it (the raw content as the body, at most `FILE_BYTES`). Any link that is not valid, or whose task no longer runs,
reads the same: 404."""

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from nestor.http import file_response, read_body
from nestor.mcp_server.access import FILE_BYTES
from nestor.mcp_server.links import Links
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
        if request.method != link.method:
            return PlainTextResponse(f"this link takes {link.method}", status_code=405)
        if link.method == "GET":
            given = next((g for g in task.given if g.blob.digest == link.target), None)
            if given is None:
                return PlainTextResponse(NO_LINK, status_code=404)
            return file_response(await self._nestor.blobs.get(given.blob.digest), given.blob.media_type, given.name)
        if (data := await read_body(request, FILE_BYTES)) is None:
            return PlainTextResponse(f"larger than {FILE_BYTES // 1_000_000} MB", status_code=413)
        self._links.used(token)
        kind = AttachmentKind.of(link.media_type)
        made = Attachment(kind=kind, data=data, media_type=link.media_type, name=link.target)
        kept = await self._nestor.tasks.add_file(task, made)
        return JSONResponse({"status": "attached", "file": kept.blob.digest, "bytes": kept.blob.size})
