import pytest

from nestor.core import Capabilities, Capability, CapabilityMissing, Component

SPEAK, SEE = Capability("audio.playback"), Capability("vision.capture")


def test_a_missing_required_capability_fails_clearly() -> None:
    available = Capabilities.union([Capabilities.of(SPEAK), Capabilities()])

    available.require(SPEAK)
    assert SEE not in available
    with pytest.raises(CapabilityMissing, match=r"'vision\.capture' is required.*available: audio\.playback"):
        available.require(SEE)


async def test_a_component_is_closed_even_when_its_user_fails() -> None:
    class Tracked(Component):
        closed = False

        async def close(self) -> None:
            self.closed = True

    component = Tracked()
    with pytest.raises(RuntimeError):
        async with component:
            raise RuntimeError("boom")
    assert component.closed
