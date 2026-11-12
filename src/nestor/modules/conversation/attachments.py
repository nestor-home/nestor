"""What comes with a message and goes with an answer, whatever the channel: files kept by content, recordings
transcribed, documents read, answers recorded in the assistant's voice. Channels only download and upload."""

import asyncio
import logging
from collections.abc import Collection, Iterable, Mapping, Sequence

from nestor.core import ProviderError
from nestor.modules.channels import Attachment, AttachmentKind, SpeechModel, TranscriptionModel
from nestor.modules.cognition.model import Image
from nestor.modules.cognition.tools import Results, ToolContext
from nestor.modules.conversation.ports import DocumentReader
from nestor.modules.conversation.types import Attached, Read
from nestor.modules.journal import BlobRef, BlobStore

logger = logging.getLogger(__name__)

HEARD = frozenset({AttachmentKind.VOICE, AttachmentKind.AUDIO})  # recordings, transcribed when kept
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

    @property
    def speaks(self) -> bool:
        return self._speech is not None

    async def keep(self, attachments: Iterable[Attachment], context: ToolContext) -> tuple[Attached, ...]:
        """Store each file, transcribe the recordings and read the documents, all at once; a recording that cannot be
        transcribed, or a document that cannot be read, is kept without its text. A document's text is readable where
        `context` is, and by its person."""
        return tuple(await asyncio.gather(*(self._keep(a, context) for a in attachments)))

    async def voice(self, text: str) -> tuple[Attachment, Attached] | None:
        """`text` recorded as a voice message, to send and as kept; `None` without a voice, or when it could not be
        recorded."""
        if self._speech is None or not text.strip():
            return None
        try:
            audio = await self._speech.synthesize(text)
        except ProviderError as error:
            logger.warning("could not record an answer in the assistant's voice: %s", error)
            return None
        blob = await self._blobs.put(audio, VOICE_TYPE)
        voice = Attachment(kind=AttachmentKind.VOICE, data=audio, media_type=VOICE_TYPE)
        return voice, Attached(kind=AttachmentKind.VOICE, blob=blob, transcript=text)

    async def sent(
        self, made: Sequence[BlobRef], sends: Collection[AttachmentKind]
    ) -> list[tuple[Attachment, Attached]]:
        """The files tools `made` that a channel which `sends` these kinds can send, to send and as kept; one no
        longer stored is left out."""
        found: list[tuple[Attachment, Attached]] = []
        for blob in made:
            kind = AttachmentKind.of(blob.media_type)
            if kind not in sends:
                continue
            try:
                data = await self._blobs.get(blob.digest)
            except KeyError:
                continue
            found.append((Attachment(kind=kind, data=data, media_type=blob.media_type), Attached(kind=kind, blob=blob)))
        return found

    async def images(self, attached: Sequence[Attached]) -> Mapping[str, Image]:
        """The pictures among `attached`, by digest, as the model looks at them; one no longer stored is left out."""
        found: dict[str, Image] = {}
        for item in attached:
            if item.kind is AttachmentKind.IMAGE and item.blob.digest not in found:
                try:
                    data = await self._blobs.get(item.blob.digest)
                except KeyError:
                    continue
                found[item.blob.digest] = Image(media_type=item.blob.media_type, data=data)
        return found

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
