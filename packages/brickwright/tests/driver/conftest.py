"""Shared fixtures for the driver tests.

Only the fixtures unique to the driver tests live here; ``response``,
``tool_call``, ``message``, and ``patch_complete`` are inherited from the
top-level ``tests/conftest.py``.
"""

import copy

import pytest

from brickwright.record import Record


class _FakeLLM:
    """Returns scripted responses in order and records the kwargs of each call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.responses[len(self.calls) - 1]


@pytest.fixture
def fake_llm():
    """Return the scripted fake-LLM class."""
    return _FakeLLM


@pytest.fixture
def assert_tool_calls_answered():
    """Assert each ``tool_calls`` turn is followed directly by one answer per call."""

    def _assert(messages: list[dict]) -> None:
        for i, message in enumerate(messages):
            expected = len(message.get("tool_calls") or [])
            if not expected:
                continue
            answers = 0
            for following in messages[i + 1 :]:
                if following.get("role") != "tool":
                    break
                answers += 1
            assert answers == expected, (
                f"turn {i} made {expected} tool call(s) but only {answers} answer(s) "
                "directly follow it"
            )

    return _assert


@pytest.fixture
def script(patch_complete, fake_llm, response, tool_call):
    """Build a fake LLM from a sequence of single-tool-call turns and install it
    as the loop's completion seam.

    Each turn is either a bare tool name (no arguments) or a ``(name, args)``
    pair; call ids are assigned ``1..n``. For turns that need usage, cost, or a
    plain-text reply, build the responses explicitly instead.
    """

    def _script(*turns):
        responses = []
        for i, turn in enumerate(turns, start=1):
            name, args = (turn, {}) if isinstance(turn, str) else turn
            responses.append(response(tool_calls=[tool_call(str(i), name, **args)]))
        return patch_complete(fake_llm(*responses))

    return _script


# A minimal build.py the loop can build, render, and finalize end to end.
_GREEN_PLATE = """\
from bricklayer import Color, LegoBuild, brick
from brickwright import TestContext

def create_build():
    m = LegoBuild()
    m.add(brick(4, 2, color=Color.GREEN))
    return m

def run_tests():
    ctx = TestContext(create_build())
    ctx.check_connected()
    ctx.check_no_collisions()
    return ctx.report()
"""


@pytest.fixture
def image_record(config, tmp_path, png_bytes):
    """A record with a prompt image and a renderable build.py."""
    img = tmp_path / "ref.png"
    img.write_bytes(png_bytes)
    rec = Record.create(config, prompt="a green plate", image=img)
    rec.write_build(_GREEN_PLATE)
    return rec


@pytest.fixture
def patch_critic(monkeypatch):
    """Install ``fn`` as the critic's completion seam, independent of the builder."""
    from brickwright.driver import critique as critique_mod

    def _install(fn):
        monkeypatch.setattr(critique_mod, "litellm_complete", lambda: fn)
        return fn

    return _install
