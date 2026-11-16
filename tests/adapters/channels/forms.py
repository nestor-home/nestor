"""What the tests of the channels that upload files share: a multipart form read back as the platform reads it."""

import email.parser
import email.policy

import httpx


def multipart(request: httpx.Request) -> tuple[dict[str, str], dict[str, tuple[str | None, bytes]]]:
    """A multipart request's text fields, and its files by field: the name each carries, and its content."""
    head = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
    form = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(head + request.content)
    fields: dict[str, str] = {}
    files: dict[str, tuple[str | None, bytes]] = {}
    for part in form.iter_parts():
        field = part.get_param("name", header="content-disposition")
        data = part.get_payload(decode=True)
        assert isinstance(field, str) and isinstance(data, bytes)
        if part.get_param("filename", header="content-disposition") is None:
            fields[field] = data.decode()
        else:
            files[field] = (part.get_filename(), data)
    return fields, files
