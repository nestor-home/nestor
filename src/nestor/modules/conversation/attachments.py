"""What comes with a message and goes with an answer, whatever the channel: files kept by content, recordings
transcribed, answers recorded in the assistant's voice. Channels only download and upload."""

import asyncio
import logging
from collections.abc import Iterable, Mapping, Sequence

from nestor.core import ProviderError
from nestor.modules.channels import Attachment, AttachmentKind, SpeechModel, TranscriptionModel
from nestor.modules.cognition.model import Image
from nestor.modules.conversation.types import Attached
from nestor.modules.journal import BlobStore

logger = logging.getLogger(__name__)

HEARD = frozenset({AttachmentKind.VOICE, AttachmentKind.AUDIO})  # recordings, transcribed when kept
VOICE_TYPE = "audio/ogg"  # what `SpeechModel.synthesize` records


class Attachments:
    """`transcription` hears recordings, `speech` records answers; without one, a recording stays unheard and answers
    stay written."""

    def __init__(
        self,
        blobs: BlobStore,
        *,
        transcription: TranscriptionModel | None = None,
        speech: SpeechModel | None = None,
    ) -> None:
        self._blobs, self._transcription, self._speech = blobs, transcription, speech

    @property
    def speaks(self) -> bool:
        return self._speech is not None

    async def keep(self, attachments: Iterable[Attachment]) -> tuple[Attached, ...]:
        """Store each file and transcribe the recordings, all at once; a recording that cannot be transcribed is
        kept without its transcript."""
        return tuple(await asyncio.gather(*(self._keep(a) for a in attachments)))

    async def voice(self, text: str) -> Attachment | None:
        """`text` recorded as a voice message; `None` without a voice, or when it could not be recorded."""
        if self._speech is None or not text.strip():
            return None
        try:
            audio = await self._speech.synthesize(text)
        except ProviderError as error:
            logger.warning("could not record an answer in the assistant's voice: %s", error)
            return None
        return Attachment(kind=AttachmentKind.VOICE, data=audio, media_type=VOICE_TYPE)

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

    async def _keep(self, attachment: Attachment) -> Attached:
        blob = await self._blobs.put(attachment.data, attachment.media_type)
        transcript = await self._transcribe(attachment) if attachment.kind in HEARD else None
        return Attached(kind=attachment.kind, blob=blob, name=attachment.name, transcript=transcript)

    async def _transcribe(self, attachment: Attachment) -> str | None:
        if self._transcription is None:
            return None
        try:
            return await self._transcription.transcribe(attachment.data, attachment.media_type)
        except ProviderError as error:
            logger.warning("could not transcribe a %s: %s", attachment.kind, error)
            return None
