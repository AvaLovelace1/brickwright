"""Tests for the record lifecycle."""

import re

import pytest

from brickwright.config import Config, Effort
from brickwright.record import (
    ID_PATTERN,
    Meta,
    Record,
    Status,
    _slugify,
    get_template,
    list_records,
    new_id,
)


class TestMetaUpdate:
    def test_update_meta_merges_and_persists(self, config):
        rec = Record.create(config, prompt="x")
        meta = rec.update_meta(status=Status.VALID, turns=3)
        assert isinstance(meta, Meta)
        reloaded = Record.load(config, rec.id).read_meta()
        assert reloaded.status is Status.VALID
        assert reloaded.turns == 3
        assert reloaded.prompt == "x"  # untouched

    def test_update_meta_rejects_unknown_fields(self, config):
        rec = Record.create(config, prompt="x")
        with pytest.raises(TypeError):
            rec.update_meta(bogus="nope")


@pytest.mark.parametrize("directory", ["snapshots_dir", "viewpoints_dir"])
def test_numbered_history_continues_after_gaps(record, directory):
    parent = getattr(record, directory)
    parent.mkdir()
    (parent / "001").mkdir()
    (parent / "003").mkdir()
    if directory == "snapshots_dir":
        created = record.add_snapshot("source", "{}").path
    else:
        created = record.new_viewpoint_session()
    assert created.name == "004"


def test_snapshot_order_remains_chronological_after_999(record):
    record.snapshots_dir.mkdir()
    for name in ("999", "1000", "002"):
        (record.snapshots_dir / name).mkdir()
    assert [snapshot.name for snapshot in record.snapshots] == ["002", "999", "1000"]


class TestCreate:
    def test_creates_the_record_layout(self, config):
        rec = Record.create(config, prompt="a red tower")
        assert rec.path.is_dir()
        assert rec.build_path.is_file()
        assert rec.out_dir.is_dir()
        assert rec.meta_path.is_file()

    def test_seeds_build_from_the_template(self, config):
        rec = Record.create(config, prompt="x")
        assert "def create_build(" in rec.read_build()

    def test_records_prompt_and_metadata(self, tmp_path):
        # model and effort come from the config
        config = Config(
            records_dir=tmp_path / "records", model="m1", effort=Effort.HIGH
        )
        rec = Record.create(config, prompt="a red tower")
        meta = rec.read_meta()
        assert meta.prompt == "a red tower"
        assert meta.generation.model == "m1"
        assert meta.generation.effort is Effort.HIGH
        assert meta.status is Status.CREATED
        assert meta.id == rec.id
        assert meta.usage is None  # populated once the driver runs
        assert meta.timing is None  # populated once the run finishes

    def test_external_defaults_to_false(self, config):
        meta = Record.create(config, prompt="x").read_meta()
        assert meta.generation.external is False

    def test_external_flag_is_recorded(self, config):
        meta = Record.create(config, prompt="x", external=True).read_meta()
        assert meta.generation.external is True

    def test_image_prompt_is_copied_in(self, config, tmp_path, png_bytes):
        img = tmp_path / "ref.png"
        img.write_bytes(png_bytes)
        rec = Record.create(config, image=img)
        meta = rec.read_meta()
        assert meta.prompt_image == "prompt.png"
        prompt_image_path = rec.prompt_image_path
        assert prompt_image_path is not None
        assert prompt_image_path.read_bytes() == png_bytes

    def test_missing_image_creates_no_partial_record(self, config, tmp_path):
        with pytest.raises(FileNotFoundError):
            Record.create(config, prompt="x", image=tmp_path / "nope.png")
        assert list_records(config) == []

    def test_from_id_clones_the_source_build(self, config):
        source = Record.create(config, prompt="original")
        source.write_build("# edited source\ndef create_build():\n    return None\n")
        clone = Record.create(config, from_id=source.id)
        assert clone.id != source.id
        assert clone.read_build() == source.read_build()

    def test_from_id_inherits_prompt_when_none_given(self, config):
        source = Record.create(config, prompt="original prompt")
        clone = Record.create(config, from_id=source.id)
        assert clone.read_meta().prompt == "original prompt"

    def test_id_carries_a_slug_from_the_prompt(self, config):
        rec = Record.create(config, prompt="a Red Castle")
        assert "red-castle" in rec.id

    def test_id_carries_a_slug_from_the_image_name(self, config, tmp_path, png_bytes):
        img = tmp_path / "red-rocket.png"
        img.write_bytes(png_bytes)
        rec = Record.create(config, image=img)
        assert "red-rocket" in rec.id

    def test_no_image_leaves_prompt_image_unset(self, config):
        rec = Record.create(config, prompt="x")
        assert rec.read_meta().prompt_image is None
        assert rec.prompt_image_path is None

    def test_fork_inherits_the_prompt_image(self, config, tmp_path, png_bytes):
        # Without this, forking an image-driven record silently disables every
        # image-based feature (critique loop, viewpoint matching) on the fork.
        img = tmp_path / "ref.png"
        img.write_bytes(png_bytes)
        source = Record.create(config, prompt="original", image=img)
        clone = Record.create(config, from_id=source.id)
        assert clone.read_meta().prompt_image == "prompt.png"
        prompt_image_path = clone.prompt_image_path
        assert prompt_image_path is not None
        assert prompt_image_path.read_bytes() == png_bytes

    def test_fork_prefers_a_newly_given_image(self, config, tmp_path, png_bytes):
        old = tmp_path / "old.png"
        old.write_bytes(png_bytes)
        new = tmp_path / "new.png"
        new.write_bytes(b"\x89PNG\r\n new")
        source = Record.create(config, prompt="original", image=old)
        clone = Record.create(config, from_id=source.id, image=new)
        prompt_image_path = clone.prompt_image_path
        assert prompt_image_path is not None
        assert prompt_image_path.read_bytes() == b"\x89PNG\r\n new"

    def test_fork_records_its_source(self, config):
        source = Record.create(config, prompt="original")
        clone = Record.create(config, from_id=source.id)
        assert clone.read_meta().forked_from == source.id

    def test_non_fork_has_no_source(self, config):
        assert Record.create(config, prompt="x").read_meta().forked_from is None


class TestLoad:
    def test_round_trips(self, config):
        rec = Record.create(config, prompt="hello")
        loaded = Record.load(config, rec.id)
        assert loaded.id == rec.id
        assert loaded.read_meta().prompt == "hello"

    @pytest.mark.parametrize("record_id", ["", "."])
    def test_the_records_dir_itself_is_not_a_record(self, config, record_id):
        Record.create(config, prompt="x")
        with pytest.raises(FileNotFoundError):
            Record.load(config, record_id)

    def test_missing_record_raises(self, config):
        with pytest.raises(FileNotFoundError):
            Record.load(config, "20990101-000000-dead")


class TestGetTemplate:
    def test_has_the_expected_scaffold(self):
        src = get_template()
        assert "def create_build(" in src
        assert "def run_tests(" in src
        assert "LegoBuild" in src
        assert "TestContext" in src  # the check harness is demonstrated

    def test_rendered_template_creates_a_valid_build(self):
        # A fresh record must be a working starting point: create_build() runs and
        # returns a grounded, collision-free model, and run_tests() passes.
        namespace: dict = {}
        exec(get_template(), namespace)
        model = namespace["create_build"]()
        assert model.placements  # not empty
        assert model.is_valid()
        # run_tests() returns CheckResult objects; the model passes every check.
        assert all(c.passed for c in namespace["run_tests"]())


class TestList:
    def test_empty_when_no_records(self, config):
        assert list_records(config) == []

    def test_lists_created_records_sorted_by_id(self, config):
        ids = sorted(Record.create(config, prompt=str(i)).id for i in range(3))
        assert [r.id for r in list_records(config)] == ids

    def test_skips_a_directory_without_metadata(self, config):
        rec = Record.create(config, prompt="x")
        (config.records_dir / "20260101-000000-deadbeef").mkdir()
        assert [r.id for r in list_records(config)] == [rec.id]

    def test_ignores_non_record_directories(self, config):
        Record.create(config, prompt="x")
        (config.records_dir / "not-a-record").mkdir()
        assert all(re.fullmatch(ID_PATTERN, r.id) for r in list_records(config))


class TestNewId:
    def test_matches_the_id_pattern(self):
        assert re.fullmatch(ID_PATTERN, new_id())

    def test_ids_are_unique(self):
        assert len({new_id() for _ in range(50)}) == 50


class TestSlugify:
    def test_lowercases_and_hyphenates_words(self):
        assert _slugify("a Red Castle") == "a-red-castle"

    def test_caps_the_number_of_words(self):
        assert _slugify("one two three four five six") == "one-two-three-four"

    def test_caps_the_length(self):
        # Four long words would exceed the 24-char limit if not truncated.
        assert len(_slugify("alpha bravo charlie delta")) <= 24

    def test_does_not_end_in_a_hyphen_when_truncation_lands_on_one(self):
        # The 24-char cut falls right after "ccccccc-"; that hyphen is trimmed.
        assert _slugify("aaaaaaa bbbbbbb ccccccc ddddddd") == "aaaaaaa-bbbbbbb-ccccccc"

    def test_empty_when_no_usable_words(self):
        assert _slugify("!!! ???") == ""
