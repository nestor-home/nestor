import pytest

from nestor.core import ContractError
from nestor.modules.satellites import group, normalize_enrollment_code, pairing_uri, parse_pairing_uri
from nestor.modules.satellites.codes import ALPHABET, new_device_code, new_enrollment_code


def test_an_enrollment_code_is_eight_unambiguous_symbols_shown_by_four() -> None:
    code = new_enrollment_code()
    assert len(code) == 8 and set(code) <= set(ALPHABET) and not set(code) & set("ILOU")
    assert group("K7QF2M9X") == "K7QF-2M9X"


@pytest.mark.parametrize("typed", ["K7QF-2M9X", "k7qf 2m9x", " k7qf-2m9x\n", "K7QF2M9X"])
def test_typing_forgives_case_dashes_and_spaces(typed: str) -> None:
    assert normalize_enrollment_code(typed) == "K7QF2M9X"


def test_letters_that_look_like_digits_read_as_digits() -> None:
    assert normalize_enrollment_code("O1IL-0000") == "01110000"


@pytest.mark.parametrize("typed", ["K7QF2M9", "K7QF2M9XY", "K7QF2M9U", "K7QF2M9!", ""])
def test_what_cannot_be_a_code_is_none(typed: str) -> None:
    assert normalize_enrollment_code(typed) is None


def test_a_device_code_is_six_digits() -> None:
    code = new_device_code()
    assert len(code) == 6 and code.isdigit()


@pytest.mark.parametrize(
    ("core", "uri"),
    [
        ("http://nestor.local:7860", "nestor+http://nestor.local:7860/?code=K7QF2M9X"),
        ("https://nestor.example.org/proxy/", "nestor+https://nestor.example.org/proxy/?code=K7QF2M9X"),
    ],
)
def test_a_pairing_uri_carries_the_core_and_the_code_both_ways(core: str, uri: str) -> None:
    assert pairing_uri(core, "K7QF2M9X") == uri
    assert parse_pairing_uri(uri) == (core.rstrip("/"), "K7QF2M9X")


def test_a_pairing_uri_is_read_leniently_for_the_code() -> None:
    assert parse_pairing_uri("NESTOR+HTTP://192.168.1.4:7860?code=k7qf-2m9x") == ("http://192.168.1.4:7860", "K7QF2M9X")


@pytest.mark.parametrize(
    "uri",
    ["http://nestor.local:7860/?code=K7QF2M9X", "nestor+http:///?code=K7QF2M9X", "nestor+http://n:1/?code=bad",
     "nestor+http://n:1/", "nestor+http://n:1/?code=K7QF2M9X&code=K7QF2M9X"],
)  # fmt: skip
def test_anything_else_is_no_pairing_uri(uri: str) -> None:
    with pytest.raises(ContractError):
        parse_pairing_uri(uri)


def test_only_an_http_core_makes_a_pairing_uri() -> None:
    with pytest.raises(ContractError):
        pairing_uri("ftp://nestor.local", "K7QF2M9X")
