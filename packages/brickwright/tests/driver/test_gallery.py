"""Tests for the narration gallery."""

import io

import pytest
from rich.console import Console

from brickwright.driver.gallery import print_gallery


@pytest.fixture
def buf() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def console(buf) -> Console:
    """A rich console writing plain text to an in-memory buffer."""
    return Console(file=buf, force_terminal=False, no_color=True, width=100)


def test_includes_every_tool_label(console, buf):
    print_gallery(console)
    out = buf.getvalue()
    for label in (
        "read",
        "write",
        "edit",
        "validate",
        "finalize",
        "explore",
        "render",
        "dispatch",
    ):
        assert label in out, f"{label} missing from the gallery"


def test_shows_both_success_and_failure_marks(console, buf):
    print_gallery(console)
    out = buf.getvalue()
    assert "✓" in out and "✗" in out


def test_print_gallery_regression(console, buf, file_regression):
    """Regression test for a specific gallery output."""
    print_gallery(console)
    out = buf.getvalue()
    file_regression.check(out)
