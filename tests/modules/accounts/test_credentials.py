"""Passwords are salted scrypt hashes; single-use tokens keep only their digest; verifier stores keep both."""

import pytest

from nestor.core import ContractError
from nestor.modules.accounts import Token, VerifierStore, hash_password, verify_password
from nestor.testing.accounts import InMemoryVerifierStore, VerifierStoreContract


def test_a_password_hash_verifies_only_its_password() -> None:
    encoded = hash_password("correct horse battery")
    assert encoded.startswith("scrypt$") and "correct" not in encoded
    assert verify_password("correct horse battery", encoded)
    assert not verify_password("correct horse batterY", encoded)
    assert encoded != hash_password("correct horse battery"), "salted"


def test_a_short_password_is_refused_and_a_malformed_hash_matches_nothing() -> None:
    with pytest.raises(ContractError, match="at least 10"):
        hash_password("short")
    for broken in ("plain-password", "scrypt$x$8$1$AA==$AA==", "bcrypt$1$2$3$AA==$AA==", "scrypt$1$2$3$!!$AA=="):
        assert not verify_password("plain-password", broken)


def test_a_token_proves_itself_against_its_digest_only() -> None:
    token = Token.issue("inv1")
    assert token.secret not in token.digest
    parsed = Token.parse(str(token))
    assert parsed == token and parsed.matches(token.digest)
    assert not Token.parse(f"inv1.{'x' * 43}").matches(token.digest)
    for broken in ("", "no-dot", ".secret", "id."):
        with pytest.raises(ContractError):
            Token.parse(broken)


class TestInMemoryVerifierStore(VerifierStoreContract):
    def store(self) -> VerifierStore:
        return InMemoryVerifierStore()


class Forgetful(InMemoryVerifierStore):
    async def forget(self, owner: str) -> None:
        return None


async def test_the_contract_rejects_a_store_that_never_forgets() -> None:
    class Broken(VerifierStoreContract):
        def store(self) -> VerifierStore:
            return Forgetful()

    with pytest.raises(AssertionError):
        await Broken().test_a_verifier_comes_back_until_it_is_replaced_or_forgotten()
