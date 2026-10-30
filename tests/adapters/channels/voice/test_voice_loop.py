"""The voice channel end to end, in real time.

Only STT and TTS are simulated; Silero VAD, Smart Turn, aggregation, interruptions and the
transport buffers are the production ones, and the assistant sits behind the `Assistant` port.
Time budgets are product requirements.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from nestor.adapters.channels.voice import SessionSettings, VoiceChannel
from nestor.core import ContractError, ProviderError
from nestor.modules.channels import Address

from .audio import needs_recordings, needs_say, recording, say, tone_wav
from .doubles import FakeAssistant, FakeSpeech, ScriptedSTT, ToneTTS
from .replay import ReplayTransport

ROOM = Address("voice", "salon")
# A short first sentence, as the persona asks: the voice starts as soon as it is complete.
LONG_REPLY = (
    "Bonne question. Alors, les ours bruns et les grizzlys sont en fait la même espèce, mais le grizzly vit "
    "à l'intérieur des terres en Amérique du Nord, et sa fourrure a des pointes argentées."
)
STT_PHRASE = "Je ne t'entends plus très bien."


@asynccontextmanager
async def serving(
    assistant: FakeAssistant,
    stt: ScriptedSTT,
    tts: ToneTTS,
    *,
    quiet_s: float = 0.5,
    clips: Path | None = None,
    send_timeout_s: float = 30.0,
) -> AsyncGenerator[VoiceChannel]:
    channel = VoiceChannel(
        "voice",
        room="salon",
        speech=FakeSpeech(stt, tts),
        session=SessionSettings(stt_phrase=STT_PHRASE, quiet_s=quiet_s),
        clips=clips,
        send_timeout_s=send_timeout_s,
    )
    async with channel:
        serve = asyncio.create_task(channel.serve(assistant))
        await asyncio.sleep(0)
        try:
            yield channel
        finally:
            await channel.close()
            await serve


async def converse(channel: VoiceChannel, transport: ReplayTransport, timeout_s: float = 60) -> None:
    """Run a session until the scenario's audio has been played."""
    session = asyncio.create_task(channel.attach(transport))
    try:
        async with asyncio.timeout(timeout_s):
            await transport.clock.input_done.wait()
    finally:
        await channel.detach(transport)
        await session


async def send_at(channel: VoiceChannel, transport: ReplayTransport, at_s: float, text: str) -> None:
    await transport.clock.sleep_until(at_s)
    await channel.send(ROOM, text)


@needs_recordings("complet-01")
async def test_the_assistant_answers_shortly_after_the_user_stops_speaking() -> None:
    rec = recording("complet-01")  # « Salut Richie, ça va ? »
    utterance, (start, end) = rec.at(0.5)
    transport = ReplayTransport([utterance], tail_s=4)
    assistant = FakeAssistant(["Ça va très bien, et toi ?"], ttft_s=0.3)
    tts = ToneTTS(transport.clock, ttfb_s=0.1)
    async with serving(assistant, ScriptedSTT(transport, [rec.text], spans=[(start, end)]), tts) as channel:
        await converse(channel, transport)

    first_sound = transport.playback.first_sound_after(end)
    assert first_sound is not None, "the assistant said nothing"
    # Simulated providers take 0.4 s: the rest is the loop's own cost (turn detection included).
    assert first_sound - end < 1.3, f"answered {first_sound - end:.2f} s after the end of speech"
    [message] = assistant.messages
    assert (message.address, message.sender.id, message.text) == (ROOM, "salon", rec.text)
    assert tts.texts == ["Ça va très bien, et toi ?"], "a healthy conversation never falls back"
    assert assistant.replies[0].heard is None, "an answer played to its end is not interrupted"


@needs_say
async def test_speech_cuts_the_assistant_off_quickly_and_it_learns_only_what_was_heard() -> None:
    question = say(0.5, "C'est quoi la différence entre un ours brun et un grizzly ?")
    barge_in_at = question.end_s + 4.0  # in the middle of the long second sentence
    barge_in = say(barge_in_at, "Attends, attends, et les ours polaires ?")
    transport = ReplayTransport([question, barge_in], tail_s=6)
    assistant = FakeAssistant([LONG_REPLY, "Les ours polaires, c'est une autre espèce."])
    stt = ScriptedSTT(transport, ["C'est quoi la différence entre un ours brun et un grizzly ?",
                                  "Attends, attends, et les ours polaires ?"])  # fmt: skip
    async with serving(assistant, stt, ToneTTS(transport.clock)) as channel:
        await converse(channel, transport)

    playback = transport.playback
    assert playback.first_sound_after(question.end_s) is not None
    cut = playback.sound_stops_after(barge_in_at)
    assert cut is not None and cut - barge_in_at < 0.5, f"cut after {cut and cut - barge_in_at:.2f} s"
    assert playback.first_sound_after(barge_in.end_s) is not None, "the question that cut in got no answer"
    first, second = assistant.replies
    assert first.heard == "Bonne question.", "only the sentence played before the cut was heard"
    assert second.heard is None


@needs_recordings("hesitation-01")
async def test_a_hesitation_mid_sentence_does_not_trigger_an_answer() -> None:
    rec = recording("hesitation-01")  # « Je voudrais que tu... euh... que tu baisses le chauffage »
    utterance, (start, end) = rec.at(0.5)
    transport = ReplayTransport([utterance], tail_s=4)
    assistant = FakeAssistant(["C'est fait."], clock=transport.clock)
    async with serving(
        assistant, ScriptedSTT(transport, [rec.text], spans=[(start, end)]), ToneTTS(transport.clock)
    ) as channel:
        await converse(channel, transport)

    assert assistant.arrivals, "the assistant never answered"
    assert assistant.arrivals[0] >= end - 0.05, "answered in the middle of the sentence"
    assert len(assistant.messages) == 1


async def _talk_over_a_monologue(item_id: str) -> tuple[float, float, ReplayTransport, FakeAssistant]:
    rec = recording(item_id)
    utterance, (start, end) = rec.at(3.0 - rec.speech_start_s)
    transport = ReplayTransport([utterance], tail_s=4)
    assistant = FakeAssistant(["D'accord, je m'arrête."])
    async with serving(
        assistant, ScriptedSTT(transport, [rec.text], spans=[(start, end)]), ToneTTS(transport.clock)
    ) as channel:
        monologue = asyncio.create_task(send_at(channel, transport, 0.1, LONG_REPLY))
        await converse(channel, transport)
        await monologue
    return start, end, transport, assistant


@needs_recordings("backchannel-01")
async def test_a_backchannel_neither_cuts_the_assistant_off_nor_reaches_it() -> None:
    start, end, transport, assistant = await _talk_over_a_monologue("backchannel-01")  # « Mmh. »
    stops = transport.playback.sound_stops_after(start, min_gap_s=0.3)
    assert stops is not None and stops > end + 1.5, "« mmh » cut the assistant off"
    assert not assistant.messages, "an acknowledgement was sent to the assistant"


@needs_recordings("interruption-01")
async def test_a_real_interruption_cuts_the_assistant_off_quickly() -> None:
    start, _, transport, assistant = await _talk_over_a_monologue("interruption-01")  # « Attends, stop. »
    cut = transport.playback.sound_stops_after(start, min_gap_s=0.3)
    assert cut is not None and cut - start < 0.6, f"cut after {cut and cut - start:.2f} s"
    assert [m.text for m in assistant.messages] == ["Attends, stop."], "the interruption got no answer"


@needs_say
async def test_an_unprompted_message_waits_until_the_user_has_been_answered() -> None:
    question = say(0.5, "Tu peux me rappeler d'acheter du pain ce soir ?")
    transport = ReplayTransport([question], tail_s=6)
    assistant = FakeAssistant(["C'est noté."])
    tts = ToneTTS(transport.clock)
    stt = ScriptedSTT(transport, ["Tu peux me rappeler d'acheter du pain ce soir ?"])
    async with serving(assistant, stt, tts) as channel:
        announcement = asyncio.create_task(send_at(channel, transport, 1.0, "Ta lessive est terminée."))
        await converse(channel, transport)
        await announcement

    assert tts.texts == ["C'est noté.", "Ta lessive est terminée."]
    (answered_at, _), (announced_at, _) = tts.spoken
    answer_ends = transport.playback.sound_stops_after(answered_at)
    assert answer_ends is not None and announced_at >= answer_ends, "the message talked over the answer"


async def test_an_unprompted_message_is_spoken_promptly_in_a_quiet_room() -> None:
    transport = ReplayTransport([], tail_s=3)
    tts = ToneTTS(transport.clock)
    async with serving(FakeAssistant([]), ScriptedSTT(transport, []), tts) as channel:
        announcement = asyncio.create_task(send_at(channel, transport, 0.5, "Ta lessive est terminée."))
        await converse(channel, transport)
        await announcement

    first_sound = transport.playback.first_sound_after(0.5)
    assert first_sound is not None and first_sound - 0.5 < 1.0, "the message waited in a quiet room"
    assert tts.texts == ["Ta lessive est terminée."]


async def test_an_unprompted_message_fails_when_nobody_is_connected() -> None:
    transport = ReplayTransport([])
    async with serving(FakeAssistant([]), ScriptedSTT(transport, []), ToneTTS(transport.clock)) as channel:
        assert not channel.reachable(ROOM)
        with pytest.raises(ProviderError) as refused:
            await channel.send(ROOM, "Ta lessive est terminée.")
    assert refused.value.transient


async def test_an_unprompted_message_not_spoken_in_time_fails_and_is_never_spoken_later() -> None:
    transport = ReplayTransport([], tail_s=2)
    tts = ToneTTS(transport.clock)
    async with serving(FakeAssistant([]), ScriptedSTT(transport, []), tts, quiet_s=1.0, send_timeout_s=0.3) as channel:
        session = asyncio.create_task(converse(channel, transport))
        await asyncio.sleep(0.1)
        assert channel.reachable(ROOM)
        with pytest.raises(ProviderError) as refused:
            await channel.send(ROOM, "Ta lessive est terminée.")
        await session
    assert refused.value.transient
    assert not tts.texts, "the sender gave up (and wrote it elsewhere): saying it now would repeat it"


async def test_closing_the_channel_ends_its_sessions_and_their_pending_messages() -> None:
    transport = ReplayTransport([], tail_s=30)
    async with serving(FakeAssistant([]), ScriptedSTT(transport, []), ToneTTS(transport.clock), quiet_s=60) as channel:
        session = asyncio.create_task(channel.attach(transport))
        await asyncio.sleep(0.2)
        pending = [asyncio.create_task(channel.send(ROOM, text)) for text in ("Ta lessive est terminée.", "Il pleut.")]
        await asyncio.sleep(0.2)
        await channel.close()
        async with asyncio.timeout(10):
            await session
            results = await asyncio.gather(*pending, return_exceptions=True)
        assert all(isinstance(r, ProviderError) and r.transient for r in results)
        assert not channel.reachable(ROOM)
        await channel.detach(transport)  # a client leaving after the session ended changes nothing
        await channel.attach(ReplayTransport([]))  # nor does one arriving once the channel is closed
        assert not channel.reachable(ROOM)


async def test_a_session_cannot_start_before_the_channel_serves_an_assistant() -> None:
    transport = ReplayTransport([])
    channel = VoiceChannel(
        "voice", room="salon", speech=FakeSpeech(ScriptedSTT(transport, []), ToneTTS(transport.clock))
    )
    async with channel:
        with pytest.raises(ContractError):
            await channel.attach(transport)


async def test_a_message_for_another_channel_is_refused() -> None:
    transport = ReplayTransport([])
    async with serving(FakeAssistant([]), ScriptedSTT(transport, []), ToneTTS(transport.clock)) as channel:
        with pytest.raises(ContractError):
            await channel.send(Address("telegram", "salon"), "Ta lessive est terminée.")


async def test_a_transcription_outage_is_announced_instead_of_silence() -> None:
    transport = ReplayTransport([], tail_s=3)
    tts = ToneTTS(transport.clock)
    async with serving(FakeAssistant([]), ScriptedSTT(transport, [], fail_at_s=0.5), tts) as channel:
        await converse(channel, transport)

    assert tts.texts == [STT_PHRASE]
    first_sound = transport.playback.first_sound_after(0.5)
    assert first_sound is not None and first_sound - 0.5 < 1.0


async def test_a_synthesis_outage_plays_the_prerecorded_clip(tmp_path: Path) -> None:
    tone_wav(tmp_path / "tts.wav", seconds=1.0)
    transport = ReplayTransport([], tail_s=4)
    tts = ToneTTS(transport.clock, down=True)
    async with serving(FakeAssistant([]), ScriptedSTT(transport, []), tts, clips=tmp_path) as channel:
        announcement = asyncio.create_task(
            send_at(channel, transport, 0.5, "Ta lessive est terminée. Pense à l'étendre.")
        )
        await converse(channel, transport)
        await announcement

    first_sound = transport.playback.first_sound_after(0.5)
    assert first_sound is not None, "no sound: the prerecorded clip was not played"
    played = transport.playback.sound_stops_after(first_sound, min_gap_s=0.3)
    assert played is not None and abs(played - first_sound - 1.0) < 0.15, "the clip was not played once, whole"


async def test_without_a_clip_a_synthesis_outage_leaves_the_assistant_silent_but_running() -> None:
    transport = ReplayTransport([], tail_s=2)
    async with serving(FakeAssistant([]), ScriptedSTT(transport, []), ToneTTS(transport.clock, down=True)) as channel:
        announcement = asyncio.create_task(send_at(channel, transport, 0.5, "Ta lessive est terminée."))
        await converse(channel, transport)
        await announcement

    assert not transport.playback.chunks


@needs_say
async def test_strangers_are_not_answered() -> None:
    question = say(0.5, "Ouvre la porte d'entrée.")
    transport = ReplayTransport([question], tail_s=3)
    assistant = FakeAssistant(["Je l'ouvre."], strangers=frozenset({"salon"}))
    async with serving(
        assistant, ScriptedSTT(transport, ["Ouvre la porte d'entrée."]), ToneTTS(transport.clock)
    ) as channel:
        await converse(channel, transport)

    assert not assistant.messages
    assert not transport.playback.chunks
