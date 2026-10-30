"""The web front: the single-page application built from `web/` (`pnpm build`), served by the admin.

`/assets/*` are content-hashed by the build, so they are cached for good; any other GET outside the API
is the application's `index.html`, which routes in the browser. Without a build, a plain page says how
to make one instead of a blank screen.
"""

import html
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from nestor.admin.api.v1 import ApiError
from nestor.admin.api.v1.language import reader_locale
from nestor.admin.presentation import Phrasebook
from nestor.admin.state import state
from nestor.core.i18n import Message

IMMUTABLE = "public, max-age=31536000, immutable"
MISSING = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><title>{title}</title></head>
<body><h1>{title}</h1><p>{text}</p></body></html>
"""


class Front:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def file(self, path: str) -> Path | None:
        """A built file at `path`, never outside the build directory."""
        candidate = (self.directory / path).resolve()
        if not candidate.is_relative_to(self.directory) or not candidate.is_file():
            return None
        return candidate

    def asset(self, path: str) -> Response:
        found = self.file(f"assets/{path}")
        if found is None:
            return Response("Fichier introuvable.", status_code=404, media_type="text/plain; charset=utf-8")
        return FileResponse(found, headers={"Cache-Control": IMMUTABLE})

    def page(self, path: str, words: Phrasebook) -> Response:
        if path.split("/", 1)[0] == "api":
            raise ApiError(404, "not_found")
        index = self.file("index.html")
        if index is None:
            title, text = (
                html.escape(words.text(Message.of(i))) for i in ("admin-front-missing-title", "admin-front-missing")
            )
            return HTMLResponse(MISSING.format(lang=words.locale, title=title, text=text), status_code=503)
        found = self.file(path) if path and path != "index.html" else None
        return FileResponse(found or index)


router = APIRouter(include_in_schema=False)


@router.get("/assets/{path:path}")
async def asset(request: Request, path: str) -> Response:
    return Front(state(request).settings.front_dir).asset(path)


@router.get("/{path:path}")
async def page(request: Request, path: str) -> Response:
    """Registered last: every GET no other route answered."""
    admin = state(request)
    words = Phrasebook(admin.nestor.localizer, reader_locale(request))
    return Front(admin.settings.front_dir).page(path, words)
