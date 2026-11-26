"""The endpoint behind `links`, at `/mcp/files/<link>`: GET downloads a file sent with the task, PUT uploads one made
for it (the raw content as the body, at most `FILE_BYTES`). Any link that is not valid reads the same: 404, and so
does any link once the turn it was given for ended, even while a later turn of its task works."""

from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

from nestor.core import ContractError
from nestor.http import file_response, read_body
from nestor.mcp_server.access import FILE_BYTES
from nestor.mcp_server.links import Links
from nestor.modules.channels import Attachment, AttachmentKind
from nestor.modules.cognition.delegation import TaskState
from nestor.runtime import Nestor

NO_LINK = "no such link"


class FileLinks:
    def __init__(self, nestor: Nestor, links: Links) -> None:
        self._nestor, self._links = nestor, links

    async def endpoint(self, request: Request) -> Response:
        token = request.path_params["token"]
        link = self._links.read(token)
        task = self._nestor.tasks.tasks.get(link.task) if link else None
        if link is None or task is None or task.state is not TaskState.WORKING or task.turn.id != link.turn:
            return PlainTextResponse(NO_LINK, status_code=404)
        if request.method != link.method:
            return PlainTextResponse(f"this link takes {link.method}", status_code=405)
        if link.method == "GET":
            given = next(g for g in task.given if g.blob.digest == link.target)  # signed for a file given
            try:
                data = await self._nestor.blobs.get(given.blob.digest)
            except KeyError:  # no longer stored
                return PlainTextResponse(NO_LINK, status_code=404)
            return file_response(data, given.blob.media_type, given.name)
        self._links.used(token)  # once, even when two requests race with it
        if (data := await read_body(request, FILE_BYTES)) is None:
            return PlainTextResponse(f"larger than {FILE_BYTES // 1_000_000} MB", status_code=413)
        kind = AttachmentKind.of(link.media_type)
        made = Attachment(kind=kind, data=data, media_type=link.media_type, name=link.target)
        try:
            kept = await self._nestor.tasks.add_file(task, link.turn, made)
        except ContractError:  # the turn ended while the file came
            return PlainTextResponse(NO_LINK, status_code=404)
        return JSONResponse({"status": "attached", "file": kept.blob.digest, "bytes": kept.blob.size})
