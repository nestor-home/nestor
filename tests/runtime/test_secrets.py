"""The configuration's secrets: named sensibly, never empty, read from a file that may not be there."""

from pathlib import Path

import pytest

from nestor.core import ContractError
from nestor.runtime.secrets import ConfigFile, open_secrets

KEY = "s" * 43


async def test_a_secret_needs_a_sensible_name_and_a_value(tmp_path: Path) -> None:
    async with open_secrets(tmp_path, KEY) as secrets:
        with pytest.raises(ContractError, match="secret name"):
            await secrets.set("../escape", "value", by="cli")
        with pytest.raises(ContractError, match="cannot be empty"):
            await secrets.set("empty", "", by="cli")
        assert await secrets.names() == []


def test_an_unreadable_configuration_file_says_so(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="cannot read"):
        ConfigFile(tmp_path / "missing.yaml", {})
    (tmp_path / "list.yaml").write_text("- not a mapping\n")
    assert ConfigFile(tmp_path / "list.yaml", {}).data_dir == Path("data")
