"""Nestor assembled from a configuration, served, stopped and restarted — with doubles only."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from nestor.cli import main
from nestor.core import ContractError
from nestor.modules.channels import Address
from nestor.modules.cognition import Outcome, TaskDelivered
from nestor.modules.cognition.model import ToolCall
from nestor.modules.conversation import AssistantTurn
from nestor.runtime import Nestor, Registry
from nestor.runtime.config import parse_config
from nestor.runtime.plugins import Family, Plugin

from .fakes import Fakes, NoSettings

CONFIG = """
data_dir: {data_dir}
persona: {{name: Richie, character: Tu es Richie.}}
household:
  - {{id: mathis, name: Mathis, accounts: ["memory:user"], reach: "memory:main"}}
model: {{kind: scripted, replies: {replies}}}
executors: [{{kind: remote, name: hermes}}]
channels: [{{kind: memory}}]
"""


def config(tmp_path: Path, replies: list[str]) -> Any:
    return parse_config(CONFIG.format(data_dir=tmp_path, replies=replies), {})


async def test_a_message_goes_through_the_whole_assistant_and_is_persisted(tmp_path: Path) -> None:
    fakes = Fakes()
    nestor = Nestor(config(tmp_path, ["Bonjour Mathis."]), fakes.registry())
    async with nestor:
        serving = asyncio.create_task(nestor.serve())
        assert await fakes.channels[0].ask("Salut") == "Bonjour Mathis."
        assert await fakes.channels[0].ask("Salut", sender="stranger") is None
        serving.cancel()

    async with Nestor(config(tmp_path, []), fakes.registry()) as restarted:
        assert [t.text for t in await restarted.journal.history(AssistantTurn)] == ["Bonjour Mathis."]
    assert (tmp_path / "nestor.db").exists()


async def test_a_task_started_before_a_restart_is_delivered_after_it(tmp_path: Path) -> None:
    fakes = Fakes()
    delegate = ToolCall("c1", "delegate_task", {"objective": "Analyse le dépôt", "notify": "message"})
    fakes.script = [delegate, "Je lance l'analyse."]
    nestor = Nestor(config(tmp_path, []), fakes.registry())
    async with nestor:
        serving = asyncio.create_task(nestor.serve())
        assert await fakes.channels[0].ask("Analyse le dépôt") == "Je lance l'analyse."
        serving.cancel()
    (ref,) = fakes.remote.runs
    fakes.remote.finish(ref, Outcome.completed("tout est vert"))

    restarted = Nestor(config(tmp_path, ["Ton analyse est finie : tout est vert."]), fakes.registry())
    async with restarted:
        delivered = restarted.journal.subscribe(TaskDelivered)
        if not await restarted.journal.history(TaskDelivered):
            await delivered.next(timeout_s=2)
    assert fakes.channels[-1].sent[0][1] == "Ton analyse est finie : tout est vert."


def test_an_unknown_adapter_kind_lists_what_is_installed(tmp_path: Path) -> None:
    text = CONFIG.format(data_dir=tmp_path, replies=[]).replace("kind: memory", "kind: carrier-pigeon")
    with pytest.raises(ContractError, match="unknown channel kind 'carrier-pigeon' \\(available: crashing, memory\\)"):
        Nestor(parse_config(text, {}), Fakes().registry())


def test_invalid_adapter_settings_name_the_adapter(tmp_path: Path) -> None:
    text = CONFIG.format(data_dir=tmp_path, replies=[]).replace("{kind: memory}", "{kind: memory, colour: red}")
    with pytest.raises(ContractError, match="channel 'memory' \\(memory\\): colour: Extra inputs"):
        Nestor(parse_config(text, {}), Fakes().registry())


def test_a_plugin_building_the_wrong_component_is_refused(tmp_path: Path) -> None:
    fakes = Fakes()
    misbuilt = Plugin(Family.CHANNEL, "memory", NoSettings, fakes.executor)
    registry = Registry([fakes.model_plugin(), fakes.executor_plugin(), misbuilt])
    with pytest.raises(ContractError, match="not a Channel"):
        Nestor(config(tmp_path, []), registry)


def test_two_channels_need_distinct_names(tmp_path: Path) -> None:
    text = CONFIG.format(data_dir=tmp_path, replies=[]).replace("[{kind: memory}]", "[{kind: memory}, {kind: memory}]")
    with pytest.raises(ContractError, match="same name"):
        Nestor(parse_config(text, {}), Fakes().registry())


def test_a_registry_refuses_two_plugins_for_one_kind() -> None:
    plugin = Fakes().channel_plugin()
    with pytest.raises(ContractError, match="two plugins provide the channel kind 'memory'"):
        Registry([plugin, plugin])


def test_the_command_line_checks_a_configuration(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "nestor.yaml"
    path.write_text(CONFIG.format(data_dir=tmp_path, replies=[]).replace("kind: scripted", "kind: absent"))
    assert main(["-c", str(path), "check"]) == 2
    assert "unknown model kind 'absent'" in capsys.readouterr().err


async def test_a_crashing_channel_does_not_stop_the_others(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    text = CONFIG.format(data_dir=tmp_path, replies=["Toujours là."]).replace(
        "[{kind: memory}]", "[{kind: memory}, {kind: crashing, name: broken}]"
    )
    fakes = Fakes()
    nestor = Nestor(parse_config(text, {}), fakes.registry())
    async with nestor:
        serving = asyncio.create_task(nestor.serve())
        assert await fakes.channels[0].ask("Salut") == "Toujours là."
        serving.cancel()
    assert "channel broken stopped" in caplog.text


async def test_initiative_settings_reach_the_courier(tmp_path: Path) -> None:
    text = CONFIG.format(data_dir=tmp_path, replies=[]) + "initiative: {quiet_hours: '22:30-07:30', main_room: salon}\n"
    nestor = Nestor(parse_config(text, {}), Fakes().registry())
    assert nestor.courier.policy.main_room == "salon"
    assert nestor.courier.policy.quiet_hours is not None and nestor.presence is None


def test_malformed_quiet_hours_are_a_configuration_error(tmp_path: Path) -> None:
    from nestor.runtime import ConfigError

    with pytest.raises(ConfigError, match="HH:MM-HH:MM"):
        parse_config(CONFIG.format(data_dir=tmp_path, replies=[]) + "initiative: {quiet_hours: late}\n", {})


def test_the_installed_adapters_are_found_through_entry_points() -> None:
    registry = Registry.installed()
    for family, kind in [
        (Family.MODEL, "openai-compatible"),
        (Family.EXECUTOR, "hermes"),
        (Family.CHANNEL, "telegram"),
    ]:
        assert registry.get(family, kind).kind == kind


async def test_the_command_line_serves_until_stopped(tmp_path: Path) -> None:
    import os
    import signal

    from nestor.runtime.app import run_until_stopped

    nestor = Nestor(config(tmp_path, []), Fakes().registry())
    asyncio.get_running_loop().call_later(0.1, os.kill, os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(run_until_stopped(nestor), timeout=5)
    assert nestor.database.path.exists()


def test_the_command_line_reports_a_valid_configuration(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "nestor.yaml"
    path.write_text(
        CONFIG.format(data_dir=tmp_path, replies=[])
        .replace("kind: scripted, replies: []", "kind: openai-compatible, api_key: k, model: m, base_url: 'http://x'")
        .replace("[{kind: remote, name: hermes}]", "[]")
        .replace("[{kind: memory}]", "[{kind: telegram, token: '1:a'}]")
    )
    assert main(["-c", str(path), "check"]) == 0
    assert "OK — 0 executor(s), channels: telegram" in capsys.readouterr().out


async def test_memories_persist_in_the_database(tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.script = [ToolCall("c1", "remember", {"text": "Le chat s'appelle Biscotte", "about": "household"}), "Noté."]
    async with Nestor(config(tmp_path, []), fakes.registry()) as nestor:
        serving = asyncio.create_task(nestor.serve())
        await fakes.channels[0].ask("Retiens que le chat s'appelle Biscotte")
        serving.cancel()
    async with Nestor(config(tmp_path, []), Fakes().registry()) as restarted:
        assert [m.text for m in await restarted.memories.recall("chat")] == ["Le chat s'appelle Biscotte"]


async def test_a_watch_created_in_conversation_is_announced_when_its_mail_arrives(tmp_path: Path) -> None:
    from nestor.modules.initiative import Incoming, WatchTriggered

    fakes = Fakes()
    fakes.script = [
        ToolCall("c1", "create_watch", {"what": "le colis", "keywords": ["Colissimo"]}),
        "Je te préviens.",
        '{"matches": true, "urgent": false, "summary": "Colis livré."}',
        "Ton colis est arrivé.",
    ]
    text = CONFIG.format(data_dir=tmp_path, replies=[]) + "inbound: [{kind: inbox}]\n"
    async with Nestor(parse_config(text, {}), fakes.registry()) as nestor:
        serving = asyncio.create_task(nestor.serve())
        assert await fakes.channels[0].ask("Préviens-moi quand le colis arrive") == "Je te préviens."
        triggered = nestor.journal.subscribe(WatchTriggered)
        fakes.inbox.deliver(Incoming(source="inbox", kind="mail", title="Votre colis Colissimo est livré"))
        await triggered.next(timeout_s=2)
        await asyncio.sleep(0.05)
        serving.cancel()
    assert fakes.channels[0].sent == [(Address("memory", "main"), "Ton colis est arrivé.")]
