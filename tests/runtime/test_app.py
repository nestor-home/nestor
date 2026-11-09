"""Nestor assembled from a configuration, served, stopped and restarted — with doubles only."""

import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import time
from pathlib import Path
from typing import Any

import pytest

from nestor.core import Component, ContractError
from nestor.modules.channels import Address, Medium, TranscriptionModel
from nestor.modules.cognition import Outcome, TaskDelivered
from nestor.modules.cognition.model import ModelRequest, ToolCall
from nestor.modules.conversation import AssistantTurn
from nestor.runtime import Backoff, Nestor, Registry
from nestor.runtime.config import ConfigError, ProblemCode, parse_config
from nestor.runtime.plugins import Family, Plugin, Services

from .fakes import Fakes, NoSettings

CONFIG = """
data_dir: {data_dir}
persona: {{name: Richie, character: Tu es Richie.}}
household:
  - {{id: mathis, name: Mathis, accounts: ["memory:user"], reach: "memory:main"}}
models: {{main: {{type: language, provider: scripted, replies: {replies}}}}}
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
        assert await fakes.channels[0].ask("Salut") == ("Bonjour Mathis.",)
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
        assert await fakes.channels[0].ask("Analyse le dépôt") == ("Je lance l'analyse.",)
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
    with pytest.raises(
        ContractError, match="no channel plugin 'carrier-pigeon' is installed \\(available: crashing, flaky, memory\\)"
    ):
        Nestor(parse_config(text, {}), Fakes().registry())


def with_embedder(tmp_path: Path, embedder: str, agent: str = "") -> Any:
    models = (
        "models: {main: {type: language, provider: scripted, replies: []}, sens: {type: embedding, provider: concepts}}"
    )
    text = CONFIG.format(data_dir=tmp_path, replies=[]).replace(
        "models: {main: {type: language, provider: scripted, replies: []}}", models
    )
    return parse_config(f"{text}memory: {{embedder: {embedder}}}\n{agent}", {})


async def test_an_embedding_model_is_declared_with_the_others_and_finds_memories_by_meaning(tmp_path: Path) -> None:
    fakes = Fakes()
    nestor = Nestor(with_embedder(tmp_path, "sens"), fakes.registry())
    assert nestor.agent.models.written is nestor.models["main"], "the embedder never answers"
    async with nestor:
        await nestor.memories.remember("Mathis est végétarien.")
        assert nestor.memories.index is not None
        await nestor.memories.index.settled()  # embedded in the background
        assert [m.text for m in await nestor.memories.recall("Du jambon ?")] == ["Mathis est végétarien."]
    with pytest.raises(ConfigError, match=r"memory\.embedder: main cannot search memories"):
        Nestor(with_embedder(tmp_path, "main"), fakes.registry())
    with pytest.raises(ConfigError, match=r"agent\.spoken: sens cannot answer"):
        Nestor(with_embedder(tmp_path, "sens", "agent: {written: sens}\n"), fakes.registry())


class HearingSettings(NoSettings):
    hears_with: str


@pytest.mark.parametrize(
    ("named", "code"),
    [("main", ProblemCode.NOT_TRANSCRIBING), ("ears", ProblemCode.UNKNOWN_MODEL)],
    ids=["another type", "unknown"],
)
def test_a_model_an_adapter_names_must_exist_and_serve_what_it_needs(
    tmp_path: Path, named: str, code: ProblemCode
) -> None:
    def build(settings: HearingSettings, name: str, services: Services) -> Component:
        services.model(settings.hears_with, TranscriptionModel, ("hears_with",))
        raise AssertionError("refused before")

    fakes = Fakes()
    hearing = Plugin(Family.CHANNEL, "hearing", HearingSettings, build)
    registry = Registry([fakes.model_plugin(), fakes.executor_plugin(), fakes.channel_plugin(), hearing])
    text = CONFIG.format(data_dir=tmp_path, replies=[]).replace(
        "[{kind: memory}]", f"[{{kind: memory}}, {{kind: hearing, hears_with: {named}}}]"
    )
    with pytest.raises(ConfigError) as refused:
        Nestor(parse_config(text, {}), registry)
    error = refused.value
    assert (error.code, error.path, error.detail) == (code, ("channels", 1, "hears_with"), named)


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
    with pytest.raises(ContractError, match="two plugins provide the channel 'memory'"):
        Registry([plugin, plugin])


def test_an_installed_entry_point_that_is_not_a_plugin_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    class Entry:  # what a broken third-party package declares in the `nestor.adapters` group
        name, value, dist = "broken", "nestor_broken:plugin", None

        def load(self) -> object:
            return object()

    monkeypatch.setattr("nestor.runtime.plugins.entry_points", lambda group: [Entry()])
    with pytest.raises(ContractError, match=r"entry point 'broken' \(nestor_broken:plugin\) is not a nestor Plugin"):
        Registry.installed()


def test_an_adapter_whose_optional_dependencies_are_missing_names_the_requirement_to_install(tmp_path: Path) -> None:
    def build(settings: NoSettings, name: str, services: Services) -> Component:
        import nestor_absent_sdk  # ty: ignore[unresolved-import]  # an optional dependency, not installed

        raise AssertionError(nestor_absent_sdk)

    fakes = Fakes()
    needy = Plugin(Family.CHANNEL, "memory", NoSettings, build, requires="nestor-home[voice]")
    registry = Registry([fakes.model_plugin(), fakes.executor_plugin(), needy])
    with pytest.raises(ContractError) as raised:
        Nestor(config(tmp_path, []), registry)
    assert str(raised.value) == (
        "channel 'memory' (memory) needs nestor-home[voice], which is not installed "
        "(no module 'nestor_absent_sdk'): pip install 'nestor-home[voice]'"
    )


def test_a_missing_module_in_an_adapter_without_optional_dependencies_is_a_bug_shown_as_such(tmp_path: Path) -> None:
    def build(settings: NoSettings, name: str, services: Services) -> Component:
        import nestor_absent_sdk  # ty: ignore[unresolved-import]

        raise AssertionError(nestor_absent_sdk)

    fakes = Fakes()
    registry = Registry(
        [fakes.model_plugin(), fakes.executor_plugin(), Plugin(Family.CHANNEL, "memory", NoSettings, build)]
    )
    with pytest.raises(ModuleNotFoundError):
        Nestor(config(tmp_path, []), registry)


# Without the `voice` extra: Pipecat (and what it brings) cannot be imported, as after `pip install nestor-home`.
WITHOUT_VOICE = """
import sys
sys.modules.update(dict.fromkeys(["pipecat", "aiortc", "numpy"], None))
from nestor.cli import main
sys.exit(main(sys.argv[1:]))
"""
OPTIONAL = """
import sys
from nestor.runtime import Family, Registry
registry = Registry.installed()
for family in (Family.MODEL, Family.EXECUTOR, Family.CHANNEL):
    print(" ".join(registry.ids(family)))
print(" ".join(sorted({m.partition(".")[0] for m in sys.modules} & {"pipecat", "aiortc", "numpy"})))
"""
TEXT_ONLY = """
data_dir: {data_dir}
persona: {{name: Nestor, character: You are Nestor.}}
household: [{{id: ada, name: Ada}}]
models:
  local: {{type: language, provider: openai-compatible, base_url: "http://localhost:11434/v1", model: llama3.2}}
channels: [{channel}]
admin: {{}}
"""


def without_voice(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "NESTOR_SECRET_KEY": "k" * 43}
    return subprocess.run(
        [sys.executable, "-c", WITHOUT_VOICE, *args], capture_output=True, text=True, timeout=60, env=env, check=False
    )


def test_discovering_the_installed_adapters_imports_no_optional_dependency() -> None:
    found = subprocess.run([sys.executable, "-c", OPTIONAL], capture_output=True, text=True, timeout=60, check=True)
    models, executors, channels, imported = found.stdout.splitlines()
    assert "openai-compatible-language" in models.split(), "found through entry points"
    assert "hermes" in executors.split()
    assert "satellites" in channels.split(), "the satellites channel is listed even when the voice extra is missing"
    assert imported == ""


def test_a_text_only_configuration_passes_the_check_without_the_voice_extra(tmp_path: Path) -> None:
    path = tmp_path / "nestor.yaml"
    path.write_text(TEXT_ONLY.format(data_dir=tmp_path, channel="{kind: telegram, token: '1:a'}"))
    checked = without_voice("-c", str(path), "check")
    assert checked.returncode == 0, checked.stderr
    assert checked.stdout.strip() == f"{path}: OK — 0 executor(s), channels: telegram, admin on 127.0.0.1:8470"


def test_satellites_in_writing_pass_the_check_without_the_voice_extra(tmp_path: Path) -> None:
    path = tmp_path / "nestor.yaml"
    path.write_text(TEXT_ONLY.format(data_dir=tmp_path, channel="{kind: satellites}"))
    checked = without_voice("-c", str(path), "check")
    assert checked.returncode == 0, checked.stderr
    assert "channels: satellites" in checked.stdout


def test_a_voice_for_satellites_without_the_extra_says_what_to_install(tmp_path: Path) -> None:
    path = tmp_path / "nestor.yaml"
    voice = "{kind: satellites, voice: {transcription: ears, speech: mouth}}"
    speech = "ears: {type: transcription, provider: elevenlabs, api_key: xi}, "
    speech += "mouth: {type: speech, provider: elevenlabs, api_key: xi, voice_id: v}"
    text = TEXT_ONLY.format(data_dir=tmp_path, channel=voice).replace("models: {", f"models: {{{speech}, ", 1)
    path.write_text(text)
    checked = without_voice("-c", str(path), "check")
    assert checked.returncode == 2
    assert checked.stderr.strip() == (
        "nestor: channel 'satellites' (satellites) needs nestor-home[voice], which is not installed "
        "(no module 'pipecat'): pip install 'nestor-home[voice]'"
    )


FAST = Backoff(initial_s=0.01, maximum_s=0.02, healthy_after_s=60)


async def test_a_crashing_channel_does_not_stop_the_others(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    text = CONFIG.format(data_dir=tmp_path, replies=["Toujours là.", "Toujours là."]).replace(
        "[{kind: memory}]", "[{kind: memory}, {kind: crashing, name: broken}]"
    )
    fakes = Fakes()
    nestor = Nestor(parse_config(text, {}), fakes.registry(), backoff=FAST)
    async with nestor:
        serving = asyncio.create_task(nestor.serve())
        assert await fakes.channels[0].ask("Salut") == ("Toujours là.",)
        await asyncio.sleep(0.1)  # the broken channel has stopped and been served again meanwhile
        assert await fakes.channels[0].ask("Encore") == ("Toujours là.",)
        serving.cancel()
    assert caplog.text.count("channel broken stopped") >= 2


async def test_a_channel_that_stopped_is_served_again_and_answers(tmp_path: Path) -> None:
    text = CONFIG.format(data_dir=tmp_path, replies=["Re-bonjour."]).replace(
        "[{kind: memory}]", "[{kind: flaky, name: memory, crashes: 2}]"
    )
    fakes = Fakes()
    nestor = Nestor(parse_config(text, {}), fakes.registry(), backoff=FAST)
    async with nestor:
        serving = asyncio.create_task(nestor.serve())
        assert await asyncio.wait_for(fakes.channels[0].ask("Salut"), 2) == ("Re-bonjour.",)
        serving.cancel()


async def test_a_channel_that_ends_when_closed_is_not_served_again(tmp_path: Path) -> None:
    fakes = Fakes()
    nestor = Nestor(config(tmp_path, []), fakes.registry(), backoff=FAST)
    async with nestor:
        serving = asyncio.create_task(nestor.serve())
        await asyncio.sleep(0.05)
        fakes.channels[0]._inbox.put_nowait(None)
        await asyncio.wait_for(serving, 1)


async def test_initiative_settings_reach_the_courier(tmp_path: Path) -> None:
    text = CONFIG.format(data_dir=tmp_path, replies=[]) + "initiative: {quiet_hours: '22:30-07:30', main_room: salon}\n"
    nestor = Nestor(parse_config(text, {}), Fakes().registry())
    assert nestor.courier.policy.main_room == "salon"
    quiet = nestor.courier.policy.quiet_hours
    assert quiet is not None and (quiet.start, quiet.end) == (time(22, 30), time(7, 30))


async def test_each_channel_brings_its_conversation_window_to_the_agent(tmp_path: Path) -> None:
    nestor = Nestor(config(tmp_path, []), Fakes().registry())
    profile = nestor.agent.channel(Address("memory", "x"))
    assert profile.ends_conversation_after_s(Medium.WRITTEN) == 4 * 3600, "writing's default"
    assert profile.ends_conversation_after_s(Medium.SPOKEN) == 300, "speech's default"


async def test_the_command_line_serves_until_stopped(tmp_path: Path) -> None:
    import os
    import signal

    from nestor.runtime.app import run_until_stopped

    nestor = Nestor(config(tmp_path, []), Fakes().registry())
    asyncio.get_running_loop().call_later(0.1, os.kill, os.getpid(), signal.SIGTERM)
    await asyncio.wait_for(run_until_stopped(nestor), timeout=5)
    assert nestor.database.path.exists()


async def test_memories_persist_in_the_database(tmp_path: Path) -> None:
    fakes = Fakes()
    fakes.script = [ToolCall("c1", "remember", {"text": "Le chat s'appelle Biscotte", "about": "household"}), "Noté."]
    async with Nestor(config(tmp_path, []), fakes.registry()) as nestor:
        serving = asyncio.create_task(nestor.serve())
        await fakes.channels[0].ask("Retiens que le chat s'appelle Biscotte")
        serving.cancel()
    async with Nestor(config(tmp_path, []), Fakes().registry()) as restarted:
        assert [m.text for m in await restarted.memories.recall("chat", vector=None)] == ["Le chat s'appelle Biscotte"]


async def test_a_watch_created_in_conversation_is_announced_when_its_mail_arrives(tmp_path: Path) -> None:
    from nestor.modules.initiative import Incoming, WatchTriggered

    def every_listed_watch(request: ModelRequest) -> str:
        ids = re.findall(r"^- \[([^\]]+)\]", request.messages[0].text, re.MULTILINE)
        return json.dumps({"matches": [{"watch": id, "summary": "Colis livré."} for id in ids]})

    fakes = Fakes()
    fakes.script = [
        ToolCall("c1", "create_watch", {"what": "le colis"}),
        "Je te préviens.",
        every_listed_watch,
        "Ton colis est arrivé.",
    ]
    text = CONFIG.format(data_dir=tmp_path, replies=[]) + "inbound: [{kind: inbox}]\n"
    async with Nestor(parse_config(text, {}), fakes.registry()) as nestor:
        serving = asyncio.create_task(nestor.serve())
        assert await fakes.channels[0].ask("Préviens-moi quand le colis arrive") == ("Je te préviens.",)
        triggered = nestor.journal.subscribe(WatchTriggered)
        fakes.inbox.deliver(Incoming(source="inbox", kind="mail", title="Votre colis Colissimo est livré"))
        await triggered.next(timeout_s=2)
        await asyncio.sleep(0.05)
        serving.cancel()
    assert fakes.channels[0].sent == [(Address("memory", "main"), "Ton colis est arrivé.")]
