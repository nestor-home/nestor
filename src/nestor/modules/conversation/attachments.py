"""What comes with a message and goes with an answer, whatever the channel: files kept by content, recordings
transcribed, documents read, answers recorded in the assistant's voice. Channels only download and upload."""

import asyncio
import logging
from collections.abc import AsyncIterator, Collection, Iterable, Mapping, Sequence

from nestor.core import ProviderError
from nestor.modules.channels import Attachment, AttachmentKind, SpeechModel, TranscriptionModel
from nestor.modules.cognition.model import Document, Image
from nestor.modules.cognition.tools import Results, ToolContext
from nestor.modules.conversation.ports import DocumentReader
from nestor.modules.conversation.types import Attached, Outgoing, Read
from nestor.modules.journal import BlobRef, BlobStore

logger = logging.getLogger(__name__)

HEARD = frozenset({AttachmentKind.VOICE, AttachmentKind.AUDIO})  # recordings, transcribed when kept
KEPT_SHOWN = 12  # files kept in memory once shown to a model, to show again next turn (a few conversations' worth)
VOICE_TYPE = "audio/ogg"  # what `SpeechModel.synthesize` records


class Attachments:
    """`transcription` hears recordings, `speech` records answers, `documents` reads documents into results the model
    reads like a long tool result's; without one, a recording stays unheard, answers stay written and documents
    unopened."""

    def __init__(
        self,
        blobs: BlobStore,
        *,
        transcription: TranscriptionModel | None = None,
        speech: SpeechModel | None = None,
        documents: tuple[DocumentReader, Results] | None = None,
    ) -> None:
        self._blobs, self._transcription, self._speech = blobs, transcription, speech
        self._documents = documents
        self._shown: dict[str, Image | Document] = {}  # the files last shown to a model, by digest

    @property
    def speaks(self) -> bool:
        return self._speech is not None

    async def keep(self, attachments: Iterable[Attachment], context: ToolContext) -> tuple[Attached, ...]:
        """Store each file, transcribe the recordings and read the documents, all at once; a recording that cannot be
        transcribed, or a document that cannot be read, is kept without its text. A document's text is readable where
        `context` is, and by its person."""
        return tuple(await asyncio.gather(*(self._keep(a, context) for a in attachments)))

    async def voice(self, text: str) -> Outgoing:
        """`text` recorded as a voice message, to send and as kept; nothing without a voice, or when it could not be
        recorded."""
        if self._speech is None or not text.strip():
            return Outgoing()
        try:
            audio = await self._speech.synthesize(text)
        except ProviderError as error:
            logger.warning("could not record an answer in the assistant's voice: %s", error)
            return Outgoing()
        blob = await self._blobs.put(audio, VOICE_TYPE)
        voice = Attachment(kind=AttachmentKind.VOICE, data=audio, media_type=VOICE_TYPE)
        return Outgoing((voice,), (Attached(kind=AttachmentKind.VOICE, blob=blob, transcript=text),))

    async def sent(self, made: Sequence[BlobRef], sends: Collection[AttachmentKind]) -> Outgoing:
        """The files tools `made` that a channel which `sends` these kinds can send, to send and as kept."""
        sendable = [blob for blob in made if AttachmentKind.of(blob.media_type) in sends]
        found = [(AttachmentKind.of(blob.media_type), blob, data) async for blob, data in self._stored(sendable)]
        return Outgoing(
            tuple(Attachment(kind=kind, data=data, media_type=blob.media_type) for kind, blob, data in found),
            tuple(Attached(kind=kind, blob=blob) for kind, blob, _ in found),
        )

    async def shown(self, attached: Sequence[Attached]) -> Mapping[str, Image | Document]:
        """`attached` as the model looks at them, by digest: pictures, and other files as documents. The same files
        come back turn after turn: the last ones are kept rather than read again."""
        named = {a.blob.digest: a for a in attached}
        missing = [a.blob for a in named.values() if a.blob.digest not in self._shown]
        async for blob, data in self._stored(missing):
            a = named[blob.digest]
            self._shown[blob.digest] = (
                Image(media_type=blob.media_type, data=data)
                if a.kind is AttachmentKind.IMAGE
                else Document(media_type=blob.media_type, data=data, name=a.name)
            )
        shown = {digest: self._shown.pop(digest) for digest in named if digest in self._shown}
        self._shown |= shown  # the latest last
        while len(self._shown) > KEPT_SHOWN:
            del self._shown[next(iter(self._shown))]
        return shown

    async def _stored(self, blobs: Iterable[BlobRef]) -> AsyncIterator[tuple[BlobRef, bytes]]:
        """Each of `blobs` with its content; one no longer stored is left out."""
        for blob in blobs:
            try:
                yield blob, await self._blobs.get(blob.digest)
            except KeyError:
                continue

    async def _keep(self, attachment: Attachment, context: ToolContext) -> Attached:
        blob = await self._blobs.put(attachment.data, attachment.media_type)
        transcript = await self._transcribe(attachment) if attachment.kind in HEARD else None
        read = await self._read(attachment, context) if attachment.kind is AttachmentKind.FILE else None
        return Attached(kind=attachment.kind, blob=blob, name=attachment.name, transcript=transcript, read=read)

    async def _read(self, attachment: Attachment, context: ToolContext) -> Read | None:
        if self._documents is None:
            return None
        reader, results = self._documents
        if not reader.reads(attachment.media_type):
            return None
        text = await reader.read(attachment.data, attachment.media_type)
        if text is None:
            return None
        return Read(await results.store(text, context) if text.strip() else None)

    async def _transcribe(self, attachment: Attachment) -> str | None:
        if self._transcription is None:
            return None
        try:
            return await self._transcription.transcribe(attachment.data, attachment.media_type)
        except ProviderError as error:
            logger.warning("could not transcribe a %s: %s", attachment.kind, error)
            return None
