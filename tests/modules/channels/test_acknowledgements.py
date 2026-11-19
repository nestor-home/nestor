"""Which words said over the assistant's voice leave it speaking: acknowledgements, in French or English."""

import pytest

from nestor.modules.channels.acknowledgements import is_acknowledgement


@pytest.mark.parametrize(
    "text",
    [
        "Mmh.",
        "Ouais.",
        "D'accord, d'accord.",
        "Ah ouais ?",
        "ok",
        "Oui oui",
        "D\u2019accord",
        "Yeah.",
        "Uh-huh.",
        "Mm-hmm.",
        "Right, right.",
        "I see.",
        "Got it.",
        "Okay, sure.",
        "All right.",
    ],
)
def test_acknowledgements_are_backchannels(text: str) -> None:
    assert is_acknowledgement(text)


@pytest.mark.parametrize(
    "text",
    [
        "Attends, stop.",
        "Non.",
        "Ok ça suffit, merci.",
        "Et les ours polaires ?",
        "Ouais mais non",
        "Excuse-moi",
        "Wait.",
        "No, stop.",
        "Yeah but what about Tom?",
        "Sorry?",
        "Hold on.",
        "Is it raining?",
    ],
)
def test_anything_else_is_a_real_turn(text: str) -> None:
    assert not is_acknowledgement(text)


def test_nothing_heard_is_not_a_backchannel() -> None:
    assert not is_acknowledgement("")
    assert not is_acknowledgement(" ... ")
