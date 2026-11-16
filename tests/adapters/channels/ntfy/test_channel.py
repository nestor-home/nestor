"""The ntfy channel against a mocked server: a notification with its words, then one a file, by its name; the words
go even when a file is refused."""

import httpx

from nestor.adapters.channels.ntfy.channel import NtfyChannel
from nestor.modules.channels import Address, Attachment, AttachmentKind, Medium
from nestor.testing.channels import DEVIS, SONG

from ..push import Recorder

PICTURE = Attachment(kind=AttachmentKind.IMAGE, data=b"png", media_type="image/png", name="dessin.png")
LEA = Address("ntfy", "lea-2f8a")


async def test_a_notification_carries_its_words_then_its_picture_with_them() -> None:
    server = Recorder()
    async with NtfyChannel("ntfy", url="https://ntfy.test", token="tk_secret", transport=server.transport) as ntfy:
        await ntfy.send(LEA, "Ton colis est arrivé.", Medium.WRITTEN, ())
        await ntfy.send(LEA, "Voilà ton dessin ✏️", Medium.WRITTEN, (PICTURE,))
    written, drawn = server.requests
    assert (written.method, written.url.path, written.content.decode()) == (
        "POST",
        "/lea-2f8a",
        "Ton colis est arrivé.",
    )
    assert (drawn.method, drawn.content) == ("PUT", b"png")
    assert dict(drawn.url.params) == {"filename": "dessin.png", "message": "Voilà ton dessin ✏️"}
    assert {r.headers["authorization"] for r in server.requests} == {"Bearer tk_secret"}


async def test_a_document_and_an_audio_file_go_one_a_notification_by_their_name() -> None:
    server = Recorder()
    async with NtfyChannel("ntfy", url="https://ntfy.test", transport=server.transport) as ntfy:
        await ntfy.send(LEA, "Le devis corrigé, et ta chanson.", Medium.WRITTEN, (DEVIS, SONG))
    assert [(r.method, r.content, dict(r.url.params)) for r in server.requests] == [
        ("PUT", DEVIS.data, {"filename": "devis.pdf", "message": "Le devis corrigé, et ta chanson."}),
        ("PUT", SONG.data, {"filename": "chanson.mp3"}),
    ]


async def test_the_words_go_when_the_server_refuses_a_file() -> None:
    sent: list[httpx.Request] = []

    def server(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and request.url.params["filename"] == "devis.pdf":
            return httpx.Response(413, json={"code": 41301, "http": 413, "error": "attachment too large"})
        sent.append(request)
        return httpx.Response(200, json={"id": "n1"})

    async with NtfyChannel("ntfy", url="https://ntfy.test", transport=httpx.MockTransport(server)) as ntfy:
        await ntfy.send(LEA, "Le devis corrigé, et ta chanson.", Medium.WRITTEN, (DEVIS, SONG))
    assert [(r.method, r.content) for r in sent] == [
        ("POST", "Le devis corrigé, et ta chanson.".encode()),
        ("PUT", SONG.data),
    ]
