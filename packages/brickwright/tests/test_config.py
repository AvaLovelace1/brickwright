"""Tests for the harness configuration."""

from pathlib import Path

from brickwright.config import RECORDS_DIR_ENV, Config


class TestRecordsDirEnv:
    def test_defaults_from_the_env_var(self, monkeypatch):
        monkeypatch.setenv(RECORDS_DIR_ENV, "/data/builds")
        assert Config().records_dir == Path("/data/builds")

    def test_falls_back_to_records_when_unset(self, monkeypatch):
        monkeypatch.delenv(RECORDS_DIR_ENV, raising=False)
        assert Config().records_dir == Path("records")

    def test_explicit_value_overrides_the_env_var(self, monkeypatch):
        monkeypatch.setenv(RECORDS_DIR_ENV, "/data/builds")
        assert Config(records_dir=Path("/tmp/x")).records_dir == Path("/tmp/x")


class TestDefaults:
    def test_sensible_numeric_defaults(self):
        c = Config()
        assert c.max_validations > 0
        assert c.max_turns > 0
        assert c.max_cost > 0
        assert c.build_timeout > 0
        assert c.render_timeout > 0

    def test_sensible_subagent_defaults(self):
        c = Config()
        assert c.subagents_enabled is False
        assert c.is_subagent is False
        assert c.max_parallel_subagents > 0
        assert c.subagent_max_turns > 0
        assert c.subagent_max_cost > 0

    def test_subagent_tiers_default_is_not_shared_between_instances(self):
        a = Config()
        b = Config()
        assert a.subagent_tiers is not b.subagent_tiers
