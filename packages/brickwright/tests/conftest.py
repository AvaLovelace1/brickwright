"""Shared fixtures for the brickwright test suite."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from brickwright.config import Config
from brickwright.record import Record
from brickwright.tools import rendering


def pytest_addoption(parser):
    parser.addoption(
        "--run-real-agent",
        action="store_true",
        default=False,
        help="run tests marked `real_agent`",
    )


def pytest_collection_modifyitems(config, items):
    """Gate real_agent tests so they only run on explicit opt-in."""
    if config.getoption("--run-real-agent"):
        return
    skip = pytest.mark.skip(
        reason="needs --run-real-agent explicitly specified (real API calls cost money)"
    )
    for item in items:
        if "real_agent" in item.keywords:
            item.add_marker(skip)


# ------- Creating records


@pytest.fixture
def config(tmp_path):
    """A Config rooted at an isolated temp records dir."""
    return Config(records_dir=tmp_path / "records")


@pytest.fixture
def record(config):
    """A freshly created record, seeded from the build template."""
    return Record.create(config, prompt="build a wall")


@pytest.fixture
def make_record(config):
    """Factory: create a record whose build.py is replaced by ``source``."""

    def _make(source):
        rec = Record.create(config, prompt="build a wall")
        rec.write_build(source)
        return rec

    return _make


@pytest.fixture
def png_bytes():
    """A tiny stand-in PNG payload for image-prompt tests."""
    return b"\x89PNG\r\n fake"


# ------- Faking resource-intensive steps


@pytest.fixture
def in_process(monkeypatch):
    """Run a record's build in-process instead of spawning a child process.

    Tests that are not about the subprocess boundary use this to skip that cost.
    Tests of the boundary must NOT use it: they need a real child process.
    """
    from brickwright.tools import build_execution

    monkeypatch.setattr(
        build_execution,
        "run_in_subprocess",
        lambda fn, args, timeout: fn(*args),
    )


@pytest.fixture
def subprocess_raises(monkeypatch):
    """Factory: make ``run_in_subprocess`` raise ``exc``.

    Lets a caller's error-wrapping be tested without spawning a real child.
    """
    from brickwright.tools import build_execution

    def _set(exc):
        def _raise(fn, args, timeout):
            raise exc

        monkeypatch.setattr(build_execution, "run_in_subprocess", _raise)

    return _set


@pytest.fixture
def fake_render_pipeline(monkeypatch):
    """Stub the heavy steps so render() runs without ldraw2mesh or a GPU."""
    monkeypatch.setattr(rendering, "_convert", lambda ldr, glb: None)
    monkeypatch.setattr(rendering, "_convert_connectivity", lambda ldr, glb: None)
    tile = np.zeros((4, 4, 4), dtype=np.uint8)
    monkeypatch.setattr(rendering, "_view_arrays", lambda glb, *, size=512: [tile] * 4)
    monkeypatch.setattr(
        rendering, "_angle_array", lambda glb, view_dir, up, *, size=512: tile
    )


# ------- Building scripted litellm responses


@pytest.fixture
def response(message):
    """Build one scripted completion. ``usage`` is ``(prompt_tokens, completion_tokens)``;
    ``cost`` mimics litellm's ``_hidden_params['response_cost']``."""

    def _response(
        content=None,
        tool_calls=None,
        usage=None,
        cost=0.0,
        reasoning_content=None,
        thinking_blocks=None,
        finish_reason=None,
    ):
        msg = message(
            content=content,
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks,
        )
        resp = SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason=finish_reason)]
        )
        if usage is not None:
            prompt, completion = usage
            resp.usage = SimpleNamespace(
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=prompt + completion,
            )
        if cost is not None:
            resp._hidden_params = {"response_cost": cost}
        return resp

    return _response


@pytest.fixture
def patch_complete(monkeypatch):
    """Make the loop drive ``fn`` instead of the real litellm completion."""
    from brickwright.driver import loop

    def _install(fn):
        monkeypatch.setattr(loop, "litellm_complete", lambda: fn)
        return fn

    return _install


@pytest.fixture
def tool_call():
    """Build one scripted ``tool_calls`` entry."""

    def _tool_call(call_id, name, **arguments):
        return SimpleNamespace(
            id=call_id,
            type="function",
            function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
        )

    return _tool_call


@pytest.fixture
def message():
    """Build one litellm-shaped assistant message (reasoning fields default None)."""

    def _message(
        content=None,
        tool_calls=None,
        reasoning_content=None,
        thinking_blocks=None,
    ):
        return SimpleNamespace(
            content=content,
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks,
        )

    return _message


# ------- Source code for a build.py file


_BUILD_TEMPLATE = """\
from bricklayer import PLATE, Color, LegoBuild, Position, brick

from brickwright import TestContext

{}

def run_tests():
    ctx = TestContext(create_build())
    ctx.check_no_floating()
    ctx.check_no_collisions()
    return ctx.report()
"""

_VALID = """\
def create_build():
    m = LegoBuild()
    m.add(brick(4, 2, color=Color.RED))
    return m
"""

_FLOATING = """\
def create_build():
    m = LegoBuild()
    m.add(brick(1, 1, color=Color.BLUE), position=Position(20, 0, 0))
    m.add(brick(4, 2, color=Color.RED), position=Position(0, 0, 1))
    return m
"""

_RAISES = """\
def create_build():
    raise RuntimeError("boom")
"""

_INFINITE = """\
def create_build():
    while True:
        pass
"""


@pytest.fixture
def valid_build():
    """Source for a build that is created and passes the builtin checks."""
    return _BUILD_TEMPLATE.format(_VALID)


@pytest.fixture
def floating_build():
    """Source for a build that is created but fails the no_floating check."""
    return _BUILD_TEMPLATE.format(_FLOATING)


@pytest.fixture
def raising_build():
    """Source whose create_build() raises RuntimeError("boom")."""
    return _BUILD_TEMPLATE.format(_RAISES)


@pytest.fixture
def infinite_build():
    """Source whose create_build() never returns."""
    return _BUILD_TEMPLATE.format(_INFINITE)
