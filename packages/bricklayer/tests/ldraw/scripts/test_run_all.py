"""Tests for the run-all extraction entry point."""

import pytest

from bricklayer.ldraw.scripts import run_all

_SCRIPT_NAMES = (
    "extract_part_geometry",
    "extract_part_meshes",
    "extract_part_connectivity",
    "extract_part_taxonomy",
    "extract_part_popularity",
)


@pytest.fixture
def stub_scripts(monkeypatch):
    """Replace each extraction ``main`` with a recording stub.

    Yields ``(recorded, codes)``: ``recorded[name]`` captures the argv the
    runner forwarded; set ``codes[name]`` to make that script "fail".
    """
    recorded: dict[str, list[str]] = {}
    codes: dict[str, int] = {}

    def install(name: str) -> None:
        def fake_main(argv=None):
            recorded[name] = list(argv or [])
            return codes.get(name, 0)

        monkeypatch.setattr(f"bricklayer.ldraw.scripts.{name}.main", fake_main)

    for name in _SCRIPT_NAMES:
        install(name)
    return recorded, codes


class TestRunAll:
    def test_runs_every_extraction_script(self, stub_scripts):
        recorded, _ = stub_scripts
        assert run_all.main([]) == 0
        assert set(recorded) == set(_SCRIPT_NAMES)
        assert all(argv == [] for argv in recorded.values())

    def test_check_is_forwarded_to_each_script(self, stub_scripts):
        recorded, _ = stub_scripts
        assert run_all.main(["--check"]) == 0
        assert all(argv == ["--check"] for argv in recorded.values())

    def test_nonzero_exit_when_any_script_fails(self, stub_scripts):
        recorded, codes = stub_scripts
        codes["extract_part_meshes"] = 2
        assert run_all.main([]) == 1
        # A failure does not abort the run; later scripts still execute.
        assert "extract_part_connectivity" in recorded

    def test_systemexit_from_a_script_is_caught(self, stub_scripts, monkeypatch):
        recorded, _ = stub_scripts

        def boom(argv=None):
            raise SystemExit("no library")

        monkeypatch.setattr("bricklayer.ldraw.scripts.extract_part_geometry.main", boom)
        assert run_all.main([]) == 1
        assert "extract_part_meshes" in recorded
        assert "extract_part_connectivity" in recorded
