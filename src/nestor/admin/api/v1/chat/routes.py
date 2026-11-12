"""The admin's chat (`agent.chat`): a person writes to the assistant from the admin, in as many chats as they like,
and reads each answer as it is written. Needs a `web` channel in the configuration and an account linked to a person
of the household. Each chat is read from the journal; its files at `/journal/{position}/attachments/{index}`."""

import base64
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.responses import StreamingResponse

from nestor.adapters.channels.web import CHAT_ID, ChatBusy, LiveAnswer, WebChannel
from nestor.admin.api.v1.chat.schemas import (
    THREAD,
    TURNS,
    ChatMessageIn,
    ChatsOut,
    ChatStreamOut,
    ChatThreadOut,
    MentionOut,
    chats,
    thread,
)
from nestor.admin.api.v1.errors import ApiError
from nestor.admin.api.v1.security import Caller, allowed
from nestor.admin.state import state
from nestor.core import PersonId
from nestor.modules.accounts import Scope
from nestor.modules.channels import Attachment, InboundMessage, Sender
from nestor.modules.journal import LogQuery

router = APIRouter(tags=["chat"])
Chatter = Annotated[Caller, Depends(allowed(Scope.AGENT_CHAT))]
ChatId = Annotated[str, Path(pattern=CHAT_ID.pattern)]
STREAM = "application/x-ndjson"
STREAMED: dict[int | str, dict[str, Any]] = {
    200: {
        "model": ChatStreamOut,
        "content": {STREAM: {}},
        "description": "The answer as it is written: one `ChatStreamOut` per line, `done` last",
    }
}


@router.get("/chats")
async def list_chats(request: Request, caller: Chatter) -> ChatsOut:
    """The caller's chats, the latest first."""
    web, person = _web(request), _person(caller)
    under = web.chats_of(person)
    entries = await state(request).nestor.journal.log.read(LogQuery(types=TURNS, sessions_under=under))
    answering = frozenset(str(a.session).removeprefix(under) for a in web.answering())
    return ChatsOut(chats=chats(entries, under, answering), sessions=under)


@router.get("/chats/mentions")
async def list_chat_mentions(request: Request, caller: Chatter) -> list[MentionOut]:
    """What the caller's messages can name with `@handle`: the household's people, the home's rooms, the executors,
    the connected accounts they may use. Any channel reads the same handles in a message's text."""
    _web(request)
    nestor = state(request).nestor
    person = nestor.household.person(_person(caller))
    return [MentionOut.of(m) for m in nestor.agent.mentions.available(person)]


@router.get("/chats/{chat}")
async def get_chat(request: Request, caller: Chatter, chat: ChatId) -> ChatThreadOut:
    """A chat's messages, oldest first, with the tools called on the way; empty for a chat not started yet."""
    web = _web(request)
    address = web.chat(_person(caller), chat)
    entries = await state(request).nestor.journal.log.read(LogQuery(types=THREAD, session=address.session))
    return ChatThreadOut(
        chat=chat,
        session=address.session,
        messages=thread(entries, caller.phrasebook),
        answering=web.following(address) is not None,
    )


@router.post("/chats/{chat}/messages", response_class=StreamingResponse, responses=STREAMED)
async def post_chat_message(request: Request, caller: Chatter, chat: ChatId, body: ChatMessageIn) -> Response:
    """Write in a chat (it starts with its first message) and stream the answer. The answer goes on if the page is
    left: `GET /chats/{chat}/answer` follows it again. 409 while the previous answer is still being written."""
    web, person = _web(request), _person(caller)
    message = InboundMessage(
        address=web.chat(person, chat),
        sender=Sender(caller.account_id or str(person), state(request).nestor.household.name_of(person, ""), person),
        text=body.text.strip(),
        attachments=tuple(
            Attachment(kind=f.kind, data=base64.b64decode(f.data), media_type=f.media_type, name=f.name)
            for f in body.files
        ),
    )
    try:
        live = web.say(message)
    except ChatBusy:
        raise ApiError(409, "chat_busy") from None
    return _stream(live)


@router.get("/chats/{chat}/answer", response_class=StreamingResponse, responses=STREAMED)
async def follow_chat_answer(request: Request, caller: Chatter, chat: ChatId) -> Response:
    """The answer being written in a chat, from its start; 204 when none is."""
    web = _web(request)
    live = web.following(web.chat(_person(caller), chat))
    return _stream(live) if live is not None else Response(status_code=204)


@router.post("/chats/{chat}/stop", status_code=204)
async def stop_chat_answer(request: Request, caller: Chatter, chat: ChatId) -> None:
    """Stop the answer being written: what was written so far stays, marked as stopped."""
    web = _web(request)
    live = web.following(web.chat(_person(caller), chat))
    if live is not None:
        await live.stop()


def _stream(live: LiveAnswer) -> StreamingResponse:
    async def lines() -> AsyncIterator[str]:
        async for part in live.parts():
            yield ChatStreamOut.of(part).model_dump_json(exclude_none=True) + "\n"
        yield ChatStreamOut(type="done").model_dump_json(exclude_none=True) + "\n"

    return StreamingResponse(lines(), media_type=STREAM, headers={"X-Accel-Buffering": "no"})


def _web(request: Request) -> WebChannel:
    channel = next((c for c in state(request).nestor.channels if isinstance(c, WebChannel)), None)
    if channel is None:
        raise ApiError(404, "chat_off")
    return channel


def _person(caller: Caller) -> PersonId:
    if caller.person is None:
        raise ApiError(403, "chat_needs_person")
    return caller.person
