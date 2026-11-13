"""What every messaging channel shares: long answers cut where a reader expects a break."""

from nestor.adapters.channels.messaging import split_text, utf16_length


def test_split_text_keeps_short_texts_whole() -> None:
    assert split_text("  Hello.  ", 100) == ["Hello."]
    assert split_text("", 100) == []


def test_split_text_prefers_a_paragraph_break_to_a_sentence_end() -> None:
    text = "One. Two.\n\nThree. Four."
    assert split_text(text, 20) == ["One. Two.", "Three. Four."]


def test_split_text_cuts_after_a_sentence_when_a_paragraph_is_too_long() -> None:
    text = "First sentence here. Second sentence there. Third one."
    assert split_text(text, 30) == ["First sentence here.", "Second sentence there.", "Third one."]


def test_split_text_cuts_a_word_longer_than_the_limit() -> None:
    assert split_text("abcdefghij", 4) == ["abcd", "efgh", "ij"]


def test_split_text_counts_as_the_platform_does() -> None:
    parts = split_text("🙂" * 5, 4, measure=utf16_length)  # an emoji is two UTF-16 units
    assert parts == ["🙂🙂", "🙂🙂", "🙂"]
