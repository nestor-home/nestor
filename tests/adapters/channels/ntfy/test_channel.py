"""The ntfy channel against a mocked server: a notification with its words, then one with its picture."""

from nestor.adapters.channels.ntfy.channel import NtfyChannel
from nestor.modules.channels import Address, Attachment, AttachmentKind, Medium

from ..push import Recorder

PICTURE = Attachment(kind=AttachmentKind.IMAGE, data=b"png", media_type="image/png", name="dessin.png")


async def test_a_notification_carries_its_words_then_its_picture_with_them() -> None:
    server = Recorder()
    async with NtfyChannel("ntfy", url="https://ntfy.test", token="tk_secret", transport=server.transport) as ntfy:
        await ntfy.send(Address("ntfy", "lea-2f8a"), "Ton colis est arrivé.", Medium.WRITTEN, ())
        await ntfy.send(Address("ntfy", "lea-2f8a"), "Voilà ton dessin ✏️", Medium.WRITTEN, (PICTURE,))
    written, drawn = server.requests
    assert (written.method, written.url.path, written.content.decode()) == (
        "POST",
        "/lea-2f8a",
        "Ton colis est arrivé.",
    )
    assert (drawn.method, drawn.content) == ("PUT", b"png")
    assert dict(drawn.url.params) == {"filename": "dessin.png", "message": "Voilà ton dessin ✏️"}
    assert {r.headers["authorization"] for r in server.requests} == {"Bearer tk_secret"}
