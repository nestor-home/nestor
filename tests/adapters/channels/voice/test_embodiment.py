from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    TTSTextFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from nestor.adapters.channels.voice.embodiment import Embodiment
from nestor.modules.behavior import Behavior, Expression
from nestor.testing.behavior import RecordingBody


class Scene:
    def __init__(self) -> None:
        self.output, self.elsewhere = FrameProcessor(), FrameProcessor()
        self.body = RecordingBody()
        self.embodiment = Embodiment(self.body, self.output)

    async def push(self, frame: Frame, *, source: FrameProcessor | None = None) -> None:
        source = source or self.elsewhere
        await self.embodiment.on_push_frame(FramePushed(source, source, frame, FrameDirection.DOWNSTREAM, 0))

    async def played(self, text: str) -> None:
        await self.push(TTSTextFrame(text, "word"), source=self.output)

    @property
    def behaviors(self) -> list[Behavior]:
        return [b for _, b in self.body.behaviors]


async def test_the_body_follows_the_turns() -> None:
    scene = Scene()
    for frame in (UserStartedSpeakingFrame(), UserStoppedSpeakingFrame(), BotStartedSpeakingFrame(),
                  BotStoppedSpeakingFrame()):  # fmt: skip
        await scene.push(frame)
    assert scene.behaviors == [Behavior.LISTENING, Behavior.THINKING, Behavior.SPEAKING, Behavior.IDLE]


async def test_cut_off_by_the_user_the_body_keeps_listening() -> None:
    scene = Scene()
    await scene.push(BotStartedSpeakingFrame())
    await scene.push(UserStartedSpeakingFrame())
    await scene.push(BotStoppedSpeakingFrame())
    assert scene.behaviors == [Behavior.SPEAKING, Behavior.LISTENING]


async def test_a_tag_animates_the_body_when_it_is_played_and_words_make_beats() -> None:
    scene = Scene()
    await scene.push(TTSTextFrame("[laughs] Pas encore joué.", "sentence"))  # not out of the speaker yet
    assert not scene.body.expressions

    await scene.played("[laughs] Ah ça,")
    await scene.played("[clears")  # a tag split across two words
    await scene.played("throat] bon.")
    assert [e for _, e in scene.body.expressions] == [Expression.JOY, Expression.AHEM]
    assert len(scene.body.beats) == 3, "tags are not words"


async def test_unknown_tags_are_not_expressions() -> None:
    scene = Scene()
    await scene.played("[dances] Voilà.")
    assert not scene.body.expressions
