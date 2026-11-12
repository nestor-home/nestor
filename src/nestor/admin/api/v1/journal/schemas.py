"""Journal entries as the front reads them, pages of them, and the counts its filters show."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from nestor.admin.api.v1.shared import MessageOut, PersonRef, ReasonOut
from nestor.admin.presentation import Kind, Tone
from nestor.core import utc_now
from nestor.modules.channels import AttachmentKind
from nestor.modules.conversation import Attached

BUCKETS_S = (60, 300, 900, 1800, 3600, 3 * 3600, 6 * 3600, 12 * 3600, 86400, 7 * 86400, 30 * 86400)
MAX_BUCKETS = 60


class LinksOut(BaseModel):
    """What threads entries together; the front builds threads and chains from these only."""

    session: str | None  # where people talk (`channel:conversation`, e.g. `telegram:42`, `voice:salon`)
    conversation: str | None  # one conversation in the session: turns within its inactivity window
    turn: str | None  # one message and all it caused: the user's message, tool calls, memories, tasks, the reply
    call: str | None  # a tool call: called, then completed
    task: str | None
    watch: str | None
    delivery: (
        str | None
    )  # what an unprompted message is about (`watch:w1`, `task:3f2a`): considered, delivered, followed up
    connection: str | None
    satellite: str | None  # a device id
    memory: str | None


class OutcomeOut(BaseModel):
    ok: bool
    duration_s: float


class AttachmentOut(BaseModel):
    """A file sent with a message; its bytes at `/journal/{position}/attachments/{index}`."""

    index: int
    kind: AttachmentKind
    media_type: str
    size: int  # in bytes
    name: str | None
    transcript: str | None  # what was said in a recording, when it could be transcribed

    @classmethod
    def of(cls, index: int, attached: Attached) -> "AttachmentOut":
        blob = attached.blob
        return cls(
            index=index,
            kind=attached.kind,
            media_type=blob.media_type,
            size=blob.size,
            name=attached.name,
            transcript=attached.transcript,
        )


class JournalItem(BaseModel):
    """One journal entry: each sentence as a message (`id` + `args`, for a front with the catalogue) and
    as text rendered by the server in the reader's language (so a plugin's events read well even when
    the front has no message for them)."""

    position: int  # grows with every entry: the cursor of pages, of the stream (`Last-Event-ID`), of `cause`
    id: str  # the event's own id
    at: datetime
    type: str  # the event type, e.g. `conversation.turn.user`
    kind: Kind
    message: MessageOut  # the summary; deliveries carry `args.follow_up` ("yes" / "no")
    text: str
    detail: str  # raw content (what was said, a tool's output): never translated; "" without
    detail_message: MessageOut | None = Field(  # a detail that is a sentence of Nestor's ("Planned: …")
        examples=[
            {"id": "journal-detail-plan", "args": {"way": "both", "spoken": "voice:salon", "written": "telegram:7"}}
        ]
    )
    detail_text: str  # what to show as detail: `detail_message` rendered, else `detail`
    reason: ReasonOut | None  # why the assistant decided to speak, when it did
    tone: Tone
    people: list[PersonRef]
    channels: list[str]
    room: str | None
    tool: str | None  # the tool called
    outcome: OutcomeOut | None  # of a tool call or a task
    attachments: list[AttachmentOut]  # the files a person sent with their message
    brand: str | None  # of the channel, connector, satellite or executor it came through
    links: LinksOut
    cause: int | None  # the position of the entry that caused this one, when known


class JournalPage(BaseModel):
    items: list[JournalItem]  # newest first
    next_before: int | None  # pass it as `before` for the next (older) page; None at the beginning


class FacetOut(BaseModel):
    key: str
    label: str
    count: int  # entries kept by every other filter: a facet ignores its own selection


class HistogramOut(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    bucket_s: int
    counts: list[int]  # entries kept by every filter, per bucket from `from`

    @classmethod
    def of(cls, moments: list[datetime], since: datetime | None, until: datetime | None) -> "HistogramOut":
        """`moments` counted in buckets over `since`..`until` (else the moments' own span), at most `MAX_BUCKETS`."""
        start = since or (min(moments) if moments else utc_now())
        end = until or (max(moments) if moments else start)
        span = max(1.0, (end - start).total_seconds())
        bucket = next((b for b in BUCKETS_S if span / b <= MAX_BUCKETS), BUCKETS_S[-1])
        counts = [0] * (int(span // bucket) + 1)
        for moment in moments:
            index = int((moment - start).total_seconds() // bucket)
            if 0 <= index < len(counts):
                counts[index] += 1
        return cls(from_=start, to=end, bucket_s=bucket, counts=counts)


class KindFacetOut(BaseModel):
    key: Kind  # labelled by the front with `journal-kind`
    count: int


class JournalFacets(BaseModel):
    total: int  # entries kept by every filter
    truncated: bool  # counted over the newest entries in range only (see the API documentation)
    kinds: list[KindFacetOut]
    people: list[FacetOut]
    channels: list[FacetOut]
    rooms: list[FacetOut]
    histogram: HistogramOut


class JournalEntryOut(BaseModel):
    item: JournalItem
    record: dict[str, Any]  # the raw logged record: type, version, id, at, source, session, payload
