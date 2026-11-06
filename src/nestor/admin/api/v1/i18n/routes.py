"""The languages the server speaks, and its catalogues for a front that renders messages itself.

Every sentence the API sends travels both as a message (`{id, args}`) and rendered (`text`). A front
using Fluent loads `GET /i18n/{locale}` — every package's catalogue, plugins' included — so it can
render the ids it receives, including those of plugins it was never built with.
"""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from nestor.admin.api.v1.i18n.schemas import LanguagesOut
from nestor.admin.api.v1.language import household_locale
from nestor.admin.state import state

router = APIRouter(tags=["i18n"])


@router.get("/i18n")
async def list_languages(request: Request) -> LanguagesOut:
    admin = state(request)
    localizer = admin.nestor.localizer
    return LanguagesOut(locales=list(localizer.locales), default=localizer.default, household=household_locale(admin))


@router.get(
    "/i18n/{locale}",
    response_class=PlainTextResponse,
    responses={200: {"description": "The catalogue in Fluent syntax", "content": {"text/plain": {}}}},
)
async def get_catalogue(request: Request, locale: str) -> PlainTextResponse:
    """The closest available locale's catalogue (named by `Content-Language`), in Fluent syntax."""
    chosen, text = state(request).nestor.localizer.source(locale)
    return PlainTextResponse(text, headers={"Content-Language": chosen})
