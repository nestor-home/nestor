"""OneDrive tools: finding the person's files, and reading one."""

from collections.abc import Callable, Mapping, Sequence

from nestor.adapters.common.text import cap
from nestor.adapters.connectors.common import SHARED
from nestor.adapters.connectors.common.api import segment
from nestor.adapters.connectors.common.tools import ask
from nestor.adapters.connectors.microsoft.graph import GraphApi
from nestor.modules.cognition.model import ToolSpec
from nestor.modules.cognition.tools import Risk, Tool, ToolContext, ToolFailed, bounded
from nestor.modules.conversation import DocumentReader

MAX_RESULTS = 20
PDF = "application/pdf"
OFFICE = (".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".odt", ".ods", ".odp", ".rtf")  # read as a PDF

SEARCH = ToolSpec(
    "onedrive_search",
    "Search the person's OneDrive for files whose name or content contains words. Returns name, type, "
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
    "onedrive_read",
    "Read the text of one OneDrive file by id (from onedrive_search): a Word, Excel or PowerPoint document, a PDF or "
    f"a text file. {SHARED}",
    {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "the file id"}},
        "required": ["id"],
    },
)


class DriveTools:
    def __init__(
        self, account: str, api: Callable[[], GraphApi], reader: DocumentReader, *, body_chars: int, max_bytes: int
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
        quoted = words.replace("'", "''")  # OData quotes a quote by doubling it
        params = [
            ("$top", str(bounded(arguments.get("max_results"), default=10, maximum=MAX_RESULTS))),
            ("$select", "id,name,file,folder,lastModifiedDateTime,webUrl"),
        ]
        found = await ask("OneDrive search", self._api().get(f"/me/drive/root/search(q='{segment(quoted)}')", params))
        files = [
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "type": "folder" if "folder" in f else (f.get("file") or {}).get("mimeType"),
                "modified": f.get("lastModifiedDateTime"),
                "link": f.get("webUrl"),
            }
            for f in found.get("value", [])
            if isinstance(f, dict)
        ]
        return {"account": self._account, "query": words, "files": files, "note": SHARED}

    async def read(self, arguments: Mapping[str, object], context: ToolContext) -> Mapping[str, object]:
        file_id = str(arguments.get("id") or "").strip()
        if not file_id:
            raise ToolFailed("give the id of a file found with onedrive_search")
        api, path = self._api(), f"/me/drive/items/{segment(file_id)}"
        item = await ask("OneDrive", api.get(path, [("$select", "id,name,file")]))
        name, media_type = str(item.get("name", "")), str((item.get("file") or {}).get("mimeType") or "")
        if not media_type:
            raise ToolFailed(f"{name} is a folder, not a document to read")
        if name.lower().endswith(OFFICE):  # OneDrive converts them; their text is the PDF's
            params, media_type = [("format", "pdf")], PDF
        elif self._reader.reads(media_type):
            params = []
        else:
            raise ToolFailed(f"{name} is {media_type}, not a document to read")
        data = await ask("OneDrive", api.download(f"{path}/content", params, max_bytes=self._max_bytes))
        text = await self._reader.read(data, media_type)
        if not text:
            raise ToolFailed(f"{name} has no text to read")
        return {"id": file_id, "name": name, "text": cap(text, self._body_chars), "note": SHARED}
