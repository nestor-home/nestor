"""Addresses and the sessions they name."""

import pytest

from nestor.core import ContractError
from nestor.modules.channels import Address


def test_an_address_round_trips_and_names_its_session() -> None:
    address = Address.parse("telegram:-1001234")

    assert address == Address("telegram", "-1001234")
    assert str(address) == "telegram:-1001234"
    assert address.session == Address("telegram", "-1001234").session != Address("voice", "-1001234").session
    with pytest.raises(ContractError, match="expected 'channel:conversation'"):
        Address.parse("telegram")
