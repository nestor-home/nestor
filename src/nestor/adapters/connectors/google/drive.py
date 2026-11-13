"""Google Drive tools: finding the person's files by their content, and reading one."""

from collections.abc import Callable, Mapping, Sequence

from nestor.adapters.common.text import cap
from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.api import segment
from nestor.adapters.connectors.common.tools import ask
from nestor.adapters.connectors.google.api import GoogleApi
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded
from nestor.modules.conversation import DocumentReader

FILES_URL = "https://www.googleapis.com/drive/v3/files"
MAX_RESULTS = 20
GOOGLE_FILES = "application/vnd.google-apps."
EXPORTS = {  # Google's own formats, read as the text they export to
    f"{GOOGLE_FILES}document": "text/plain",
    f"{GOOGLE_FILES}spreadsheet": "text/csv",
    f"{GOOGLE_FILES}presentation": "text/plain",
}

SEARCH = ToolSpec(
    "google_drive_search",
    "Search the person's Google Drive for files whose name or content contains words. Returns name, type, "
    f"modification date, link and id of each. {SHARED}",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "words to find, e.g. 'contrat assurance habitation'"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_RESULTS, "default": 10},
        },
        "required": ["query"],
    },
)
READ = ToolSpec(
    "google_drive_read",
    "Read the text of one Google Drive file by id (from google_drive_search): a Google Doc, Sheet (as CSV) or "
    f"Slides, a PDF or a text file. {SHARED}",
    {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "the file id"}},
        "required": ["id"],
    },
)


class DriveTools:
    def __init__(
        self, account: str, api: Callable[[], GoogleApi], reader: DocumentReader, *, body_chars: int, max_bytes: int
    ) -> None:
        self._account, self._api, self._reader = account, api, reader
        self._body_chars, self._max_bytes = body_chars, max_bytes

    def tools(self) -> Sequence[Tool]:
        return (
            Tool(spec=SEARCH, run=self.search, risk=Risk.READ, timeout_s=20.0),
            Tool(spec=READ, run=self.read, risk=Risk.READ, timeout_s=60.0),
        )

    async def search(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        words = str(arguments.get("query") or "").strip()
        if not words:
            raise ToolFailed("give words to search for")
        quoted = words.replace("\\", "\\\\").replace("'", "\\'")
        params = [
            ("q", f"fullText contains '{quoted}' and trashed = false"),
            ("fields", "files(id,name,mimeType,modifiedTime,webViewLink)"),
            ("pageSize", str(bounded(arguments.get("max_results"), default=10, maximum=MAX_RESULTS))),
        ]
        found = await ask("Google Drive search", self._api().get(FILES_URL, params))
        files = [
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "type": f.get("mimeType"),
                "modified": f.get("modifiedTime"),
                "link": f.get("webViewLink"),
            }
            for f in found.get("files", [])
            if isinstance(f, dict)
        ]
        return {"account": self._account, "query": words, "files": files, "note": SHARED}

    async def read(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        file_id = str(arguments.get("id") or "").strip()
        if not file_id:
            raise ToolFailed("give the id of a file found with google_drive_search")
        api, url = self._api(), f"{FILES_URL}/{segment(file_id)}"
        meta = await ask("Google Drive", api.get(url, [("fields", "id,name,mimeType")]))
        name, media_type = str(meta.get("name", "")), str(meta.get("mimeType", ""))
        if exported := EXPORTS.get(media_type):
            url, params, media_type = f"{url}/export", [("mimeType", exported)], exported
        elif media_type.startswith(GOOGLE_FILES) or not self._reader.reads(media_type):
            raise ToolFailed(f"{name} is {media_type}, not a document to read")
        else:
            params = [("alt", "media")]
        data = await ask("Google Drive", api.download(url, params, max_bytes=self._max_bytes))
        text = await self._reader.read(data, media_type)
        if not text:
            raise ToolFailed(f"{name} has no text to read")
        return {"id": file_id, "name": name, "text": cap(text, self._body_chars), "note": SHARED}
