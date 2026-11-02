"""The Docker files: one source of truth for the secrets, a local model reachable from the container, and
the ports Nestor listens on by default."""

import re
from pathlib import Path

import yaml

from nestor.adapters.channels.satellites import SatellitesSettings
from nestor.runtime.config import AdminConfig

ROOT = Path(__file__).parents[1]
COMPOSE = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]["nestor"]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
ADMIN, VOICE = AdminConfig().port, SatellitesSettings.model_fields["port"].default
# Ports local model servers and common tools take by default: Nestor's must not collide with them.
TAKEN = {1234, 3000, 5000, 5173, 7860, 8000, 8080, 8081, 8123, 8888, 11434}


def test_the_dot_env_is_read_by_nestor_alone_so_a_restart_applies_an_edit() -> None:
    assert "env_file" not in COMPOSE and "environment" not in COMPOSE


def test_a_model_server_on_the_host_is_reachable_from_the_container() -> None:
    assert "host.docker.internal:host-gateway" in COMPOSE["extra_hosts"]


def test_the_default_ports_are_distinct_and_clear_of_common_local_servers() -> None:
    assert ADMIN != VOICE
    assert not {ADMIN, VOICE} & TAKEN


def test_the_container_publishes_and_checks_the_default_ports() -> None:
    assert sorted(COMPOSE["ports"]) == [f"{ADMIN}:{ADMIN}", f"{VOICE}:{VOICE}"]
    exposed = re.search(r"^EXPOSE (.+)$", DOCKERFILE, re.MULTILINE)
    assert exposed and sorted(map(int, exposed[1].split())) == sorted([ADMIN, VOICE])
    assert f"http://127.0.0.1:{ADMIN}/health" in DOCKERFILE
