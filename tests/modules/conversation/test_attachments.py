"""Files sent with a message, whatever the channel: kept by content, recordings transcribed, images shown to a model
that sees them, and what the model cannot open said to it rather than dropped."""

import re

import pytest

from nestor.adapters.documents import FileReader
from nestor.modules.channels import Address, Attachment, AttachmentKind, InboundMessage, Sender
from nestor.modules.cognition.images import ImageTools
from nestor.modules.cognition.model import ModelRequest, Role, ToolCall
from nestor.modules.cognition.tools import Results
from nestor.modules.conversation import AnswerAttached, Attachments, ChannelProfile, UserTurn
from nestor.modules.conversation.conversations import DOCUMENTS, IMAGES
from nestor.modules.conversation.history import IMAGE_BYTES
from nestor.modules.journal import Journal
from nestor.testing.channels import OGG, ScriptedSpeech, ScriptedTranscription
from nestor.testing.cognition.images import PNG, ScriptedImages
from nestor.testing.cognition.model import ScriptedModel
from nestor.testing.documents import text_pdf
from nestor.testing.journal import MemoryBlobStore

from .conftest import TELEGRAM, MakeAgent

PHOTO = Attachment(kind=AttachmentKind.IMAGE, data=b"jpeg bytes", media_type="image/jpeg")
VOICE_NOTE = Attachment(kind=AttachmentKind.VOICE, data=b"rappelle-moi le pain", media_type="audio/ogg")
SPEAKING = {"telegram": ChannelProfile(sends=frozenset({AttachmentKind.VOICE}))}


def sent(text: str = "", *attachments: Attachment) -> InboundMessage:
    return InboundMessage(address=TELEGRAM, sender=Sender("42"), text=text, attachments=attachments)


def last_user(request: ModelRequest):
    return [m for m in request.messages if m.role is Role.USER][-1]


class Seeing(ScriptedModel):
    vision = True


class ReadingPdfs(ScriptedModel):
    reads = frozenset({"application/pdf"})


async def test_a_voice_message_is_kept_heard_and_logged_as_the_person_s_words(
    make_agent: MakeAgent, journal: Journal
) -> None:
    blobs, model = MemoryBlobStore(), ScriptedModel("C'est noté.")
    agent = make_agent(model=model, attachments=Attachments(blobs, transcription=ScriptedTranscription()))
    assert await agent.respond(sent("", VOICE_NOTE)).collect() == ("C'est noté.",)
    [turn] = await journal.history(UserTurn)
    assert turn.text == "rappelle-moi le pain", "what was said is the person's words: memory and the admin read them"
    [kept] = turn.attachments
    assert (kept.kind, kept.transcript) == (AttachmentKind.VOICE, "rappelle-moi le pain")
    assert blobs.blobs[kept.blob.digest] == VOICE_NOTE.data
    assert last_user(model.requests[0]).content == "[Said in a voice message:]\nrappelle-moi le pain"


async def test_a_voice_message_that_cannot_be_transcribed_is_said_so_to_the_model(make_agent: MakeAgent) -> None:
    model = ScriptedModel("Je n'ai pas pu l'écouter.")
    attachments = Attachments(MemoryBlobStore(), transcription=ScriptedTranscription(failing=True))
    agent = make_agent(model=model, attachments=attachments)
    await agent.respond(sent("", VOICE_NOTE)).collect()
    assert "could not listen" in last_user(model.requests[0]).content


async def test_a_model_that_sees_images_receives_them_and_one_that_does_not_is_told(make_agent: MakeAgent) -> None:
    seeing, blind = Seeing("Joli."), ScriptedModel("Je ne vois pas les images.")
    for model in (seeing, blind):
        agent = make_agent(model=model, attachments=Attachments(MemoryBlobStore()))
        await agent.respond(sent("regarde", PHOTO)).collect()
    shown = last_user(seeing.requests[0])
    assert [i.data for i in shown.images] == [PHOTO.data]
    assert shown.content == "[An image, attached]\nregarde"
    hidden = last_user(blind.requests[0])
    assert hidden.images == ()
    assert "you cannot see" in hidden.content


async def test_only_the_last_images_of_a_conversation_are_shown_again(make_agent: MakeAgent) -> None:
    model = Seeing()
    agent = make_agent(model=model, attachments=Attachments(MemoryBlobStore()))
    photos = [
        Attachment(kind=AttachmentKind.IMAGE, data=f"photo {i}".encode(), media_type="image/png") for i in range(6)
    ]
    for photo in photos:
        await agent.respond(sent("", photo)).collect()
    users = [m for m in model.requests[-1].messages if m.role is Role.USER]
    shown = [i.data for m in users for i in m.images]
    assert shown == [p.data for p in photos[-IMAGES:]]
    assert "sent earlier" in users[0].content


async def test_an_image_too_large_for_the_providers_is_only_mentioned(make_agent: MakeAgent) -> None:
    model = Seeing()
    agent = make_agent(model=model, attachments=Attachments(MemoryBlobStore()))
    poster = Attachment(kind=AttachmentKind.IMAGE, data=b"x" * (IMAGE_BYTES + 1), media_type="image/png")
    await agent.respond(sent("", poster)).collect()
    await agent.respond(sent("et alors ?")).collect()
    for request in model.requests:
        first = next(m for m in request.messages if m.role is Role.USER)
        assert (first.images, first.content) == ((), "[An image too large for you to see]")


async def test_a_file_the_model_cannot_open_is_named_to_it(make_agent: MakeAgent) -> None:
    model = ScriptedModel("Je ne peux pas ouvrir ce fichier.")
    agent = make_agent(model=model, attachments=Attachments(MemoryBlobStore()))
    pdf = Attachment(kind=AttachmentKind.FILE, data=b"%PDF", media_type="application/pdf", name="devis.pdf")
    await agent.respond(sent("tu peux lire ?", pdf)).collect()
    assert (
        last_user(model.requests[0]).content
        == "[A file (devis.pdf), application/pdf, that you cannot open]\ntu peux lire ?"
    )


async def test_a_document_is_read_by_the_model_where_it_was_sent_and_nowhere_else(
    make_agent: MakeAgent, journal: Journal
) -> None:
    blobs = MemoryBlobStore()
    results = Results(journal, blobs)

    def read_it(request: ModelRequest) -> ToolCall:
        ref = re.search(r"ref='(\w+)'", last_user(request).content)
        return ToolCall("call-1", "read_result", {"ref": ref.group(1) if ref else ""})

    model = ScriptedModel(read_it, "Le total est de 1200 euros.")
    attachments = Attachments(blobs, documents=(FileReader(), results))
    agent = make_agent(model=model, attachments=attachments, results=results)
    devis = Attachment(
        kind=AttachmentKind.FILE,
        data=text_pdf("Devis 42\nTotal 1200 EUR"),
        media_type="application/pdf",
        name="devis.pdf",
    )
    assert await agent.respond(sent("c'est combien ?", devis)).collect() == ("Le total est de 1200 euros.",)
    assert last_user(model.requests[0]).content.startswith("[A document (devis.pdf): read its text with read_result")
    [read] = [m for m in model.requests[1].messages if m.role is Role.TOOL]
    assert "Total 1200 EUR" in str(read.content)

    ref = re.search(r"ref='(\w+)'", last_user(model.requests[0]).content)
    assert ref is not None
    elsewhere = ScriptedModel(ToolCall("call-2", "read_result", {"ref": ref.group(1)}), "Je ne peux pas.")
    other = make_agent(model=elsewhere, attachments=attachments, results=results)
    await other.respond(InboundMessage(address=Address("telegram", "77"), sender=Sender("77"), text="lis-le")).collect()
    [refused] = [m for m in elsewhere.requests[1].messages if m.role is Role.TOOL]
    assert "was given here" in str(refused.content), "a document is read where it was sent, or by who sent it"


@pytest.mark.parametrize("shows_pictures", [True, False], ids=["channel-shows-pictures", "channel-shows-none"])
async def test_a_picture_a_tool_drew_goes_with_the_last_message_where_the_channel_shows_pictures(
    make_agent: MakeAgent, journal: Journal, shows_pictures: bool
) -> None:
    blobs = MemoryBlobStore()
    drawing = ToolCall("call-1", "generate_image", {"description": "un galet en noeud papillon"})
    model = ScriptedModel(drawing, "Voilà ton dessin.")
    sends = frozenset({AttachmentKind.IMAGE}) if shows_pictures else frozenset()
    agent = make_agent(
        model=model,
        tools=ImageTools(ScriptedImages()).tools(),
        attachments=Attachments(blobs),
        blobs=blobs,
        channels={"telegram": ChannelProfile(sends=sends)},
    )
    [answer] = [a async for a in agent.respond(sent("dessine-moi Nestor")).answers()]

    picture = PNG + b"un galet en noeud papillon"
    assert answer.text == "Voilà ton dessin."
    assert [(a.kind, a.data, a.media_type) for a in answer.attachments] == (
        [(AttachmentKind.IMAGE, picture, "image/png")] if shows_pictures else []
    )
    attached = await journal.history(AnswerAttached)
    assert [[blobs.blobs[f.blob.digest] for f in a.files] for a in attached] == ([[picture]] if shows_pictures else [])


@pytest.mark.parametrize(
    ("channels", "speech", "voiced"),
    [(SPEAKING, ScriptedSpeech(), True), (None, ScriptedSpeech(), False), (SPEAKING, None, False)],
    ids=["channel-and-voice", "channel-without-voice-messages", "no-voice"],
)
async def test_an_answer_to_a_voice_message_goes_back_recorded_and_written_to_be_heard(
    make_agent: MakeAgent, channels: dict | None, speech: ScriptedSpeech | None, voiced: bool
) -> None:
    model = ScriptedModel("D'accord.")
    attachments = Attachments(MemoryBlobStore(), transcription=ScriptedTranscription(), speech=speech)
    agent = make_agent(model=model, attachments=attachments, channels=channels)
    [answer] = [a async for a in agent.respond(sent("", VOICE_NOTE)).answers()]
    system = model.requests[0].messages[0].content
    assert ("goes back as a voice message" in system) is voiced
    recorded = answer.voice
    assert (recorded is not None) is voiced
    if recorded is not None:
        assert (recorded.media_type, recorded.data) == ("audio/ogg", OGG + b"D'accord.")


async def test_an_answer_that_cannot_be_recorded_is_written(make_agent: MakeAgent) -> None:
    speech = ScriptedSpeech(failing=True)
    attachments = Attachments(MemoryBlobStore(), transcription=ScriptedTranscription(), speech=speech)
    agent = make_agent(model=ScriptedModel("Le pain est noté."), attachments=attachments, channels=SPEAKING)
    [answer] = [a async for a in agent.respond(sent("", VOICE_NOTE)).answers()]
    assert (answer.text, answer.voice) == ("Le pain est noté.", None)


async def test_a_model_that_reads_pdfs_gets_the_last_ones_whole_and_the_others_as_text(
    make_agent: MakeAgent, journal: Journal
) -> None:
    model, blobs = ReadingPdfs(), CountedBlobStore()
    agent = make_agent(model=model, attachments=Attachments(blobs, documents=(FileReader(), Results(journal, blobs))))
    pdfs = [
        Attachment(kind=AttachmentKind.FILE, data=text_pdf(f"Devis {i}"), media_type="application/pdf", name=f"{i}.pdf")
        for i in range(3)
    ]
    for pdf in pdfs:
        await agent.respond(sent("", pdf)).collect()

    users = [m for m in model.requests[-1].messages if m.role is Role.USER]
    assert [(d.name, d.data) for m in users for d in m.documents] == [(p.name, p.data) for p in pdfs[-DOCUMENTS:]]
    assert re.fullmatch(
        r"\[A document \(2\.pdf\), attached; its text also with read_result\(ref='\w+'\)\]", users[-1].content
    ), "a fallback that does not read it whole can still read its text"
    assert users[0].content.startswith("[A document (0.pdf): read its text with read_result"), "an older one is read"
    assert set(blobs.reads.values()) == {1}, "a file shown again next turn is not read again"


class CountedBlobStore(MemoryBlobStore):
    def __init__(self) -> None:
        super().__init__()
        self.reads: dict[str, int] = {}

    async def get(self, digest: str) -> bytes:
        self.reads[digest] = self.reads.get(digest, 0) + 1
        return await super().get(digest)


async def test_the_files_of_one_request_stay_within_what_providers_take(make_agent: MakeAgent) -> None:
    model = ReadingPdfs()
    agent = make_agent(model=model, attachments=Attachments(MemoryBlobStore()))
    heavy = [
        Attachment(kind=AttachmentKind.FILE, data=bytes([i]) * 9_000_000, media_type="application/pdf", name=f"{i}.pdf")
        for i in range(2)
    ]
    for pdf in heavy:
        await agent.respond(sent("", pdf)).collect()

    users = [m for m in model.requests[-1].messages if m.role is Role.USER]
    assert [d.name for m in users for d in m.documents] == ["1.pdf"], "two would weigh more than a request may"
