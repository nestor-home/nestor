"""Documents read without any service: a PDF by its text layer, page after page, a text file in its charset, and
what cannot be read said so rather than raised."""

import pytest

from nestor.adapters.documents import FileReader
from nestor.testing.documents import text_pdf


async def test_a_pdf_reads_page_after_page() -> None:
    text = await FileReader().read(text_pdf("Devis 42\nTotal 1200 EUR", "Conditions"), "application/pdf")
    assert text == "[page 1]\nDevis 42\nTotal 1200 EUR\n\n[page 2]\nConditions"


@pytest.mark.parametrize(
    ("data", "read"),
    [(text_pdf(""), ""), (b"%PDF-1.4\nnot really", None)],
    ids=["no-text-like-a-scan", "damaged"],
)
async def test_a_pdf_without_text_reads_empty_and_a_damaged_one_reads_as_nothing(data: bytes, read: str | None) -> None:
    assert await FileReader().read(data, "application/pdf") == read


async def test_a_text_file_reads_in_its_charset_and_other_files_are_not_read() -> None:
    reader = FileReader()
    assert await reader.read("Liste: café, crème".encode("latin-1"), "text/plain; charset=ISO-8859-1") == (
        "Liste: café, crème"
    )
    assert not reader.reads("image/png")
    assert reader.reads("application/pdf") and reader.reads("text/csv")
