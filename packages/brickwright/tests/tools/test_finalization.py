"""Tests for the finalization tool."""

import pytest

from brickwright.tools import finalize, rendering


class TestFinalize:
    def test_rejects_collision_even_when_custom_tests_omit_it(
        self,
        record,
        in_process,
        monkeypatch,
    ):
        monkeypatch.setattr(rendering, "render_available", lambda: False)
        record.write_build("""import bricklayer as bl
def create_build():
    m = bl.LegoBuild()
    m.add(bl.Element("3001", bl.Color.RED))
    m.add(bl.Element("3001", bl.Color.BLUE))
    return m
def run_tests():
    return []
""")
        result = finalize(record)
        assert not result.ok
        assert result.validation is not None
        assert "no_collisions" in result.validation.failed_checks
        assert not record.read_meta().finalized
        assert not record.ldr_path.exists()

    def test_edit_during_export_rejects_the_superseded_result(
        self, record, in_process, floating_build, monkeypatch
    ):
        monkeypatch.setattr(rendering, "render_available", lambda: False)
        original_source = record.read_build()
        export = rendering.build_ldraw

        def concurrent_edit(rec, model=None):
            path = export(rec, model)
            rec.build_path.write_text(floating_build)
            return path

        monkeypatch.setattr(rendering, "build_ldraw", concurrent_edit)
        report = finalize(record)
        assert not report.ok
        assert report.validation is not None
        assert report.validation.error_type == "SourceChanged"
        assert record.snapshots[-1].read_build() == original_source
        assert not record.read_meta().finalized
        assert not record.ldr_path.exists()

    def test_revalidates_source_edited_outside_the_tools(
        self, record, in_process, floating_build, monkeypatch
    ):
        from brickwright.tools import validate

        monkeypatch.setattr(rendering, "render_available", lambda: False)
        validate(record)
        record.build_path.write_text(floating_build)
        report = finalize(record)
        assert not report.ok
        assert report.validation is not None and not report.validation.ok
        assert not record.read_meta().finalized
        assert not record.ldr_path.exists()

    def test_validation_and_export_share_one_build(
        self, record, in_process, monkeypatch
    ):
        monkeypatch.setattr(rendering, "render_available", lambda: False)
        source = record.read_build().replace(
            "def create_build():",
            "builds = 0\n\ndef create_build():\n"
            "    global builds\n    builds += 1\n    assert builds == 1\n",
        )
        record.write_build(source)
        report = finalize(record)
        assert report.ok, report.error
        meta = record.read_meta()
        assert meta.finalized
        assert meta.exported_source_sha256 == meta.validated_source_sha256
        assert meta.exported_source_sha256 == record.source_sha256

    def test_failed_export_clears_previous_finalization(
        self, record, in_process, monkeypatch
    ):
        monkeypatch.setattr(rendering, "render_available", lambda: False)
        assert finalize(record).ok
        monkeypatch.setattr(rendering, "render_available", lambda: True)

        def fail(*args, **kwargs):
            raise RuntimeError("render unavailable")

        monkeypatch.setattr(rendering, "build_mesh", fail)
        report = finalize(record)
        assert not report.ok
        assert not record.read_meta().finalized
        assert record.read_meta().exported_source_sha256 is None
        assert not record.ldr_path.exists()

    def test_renders_the_model_to_ldraw(
        self, make_record, in_process, valid_build, monkeypatch
    ):
        monkeypatch.setattr(rendering, "render_available", lambda: False)
        rec = make_record(valid_build)
        report = finalize(rec)
        assert report.ok is True
        assert report.error is None
        assert rec.ldr_path.is_file()
        assert rec.ldr_path.read_text().strip()  # not empty
        assert (rec.out_dir / "diagnostics" / "build.ldr").is_file()
        assert not (rec.out_dir / "diagnostics" / "build.glb").exists()

    def test_renders_a_png_when_a_library_is_available(
        self, make_record, in_process, valid_build, fake_render_pipeline, monkeypatch
    ):
        monkeypatch.setattr(rendering, "render_available", lambda: True)
        monkeypatch.setattr(
            rendering, "_convert", lambda ldr, glb: glb.write_bytes(b"mesh")
        )
        rec = make_record(valid_build)
        report = finalize(rec)
        assert report.ok is True
        assert report.error is None
        assert rec.ldr_path.is_file()
        assert rec.render_path.is_file()
        assert rec.render_path.stat().st_size > 0
        assert (rec.out_dir / "diagnostics" / "build.ldr").is_file()
        assert (rec.out_dir / "diagnostics" / "build.glb").is_file()

    def test_skips_rendering_when_no_library_is_available(
        self, make_record, in_process, valid_build, monkeypatch
    ):
        monkeypatch.setattr(rendering, "render_available", lambda: False)
        rec = make_record(valid_build)
        report = finalize(rec)
        assert report.ok is True
        assert rec.ldr_path.is_file()
        assert not rec.render_path.is_file()

    def test_build_error_is_reported_and_nothing_is_rendered(
        self, make_record, in_process, raising_build, monkeypatch
    ):
        monkeypatch.setattr(rendering, "render_available", lambda: True)
        rec = make_record(raising_build)
        report = finalize(rec)
        assert report.ok is False
        assert report.error is not None
        assert "RuntimeError" in report.error
        assert "boom" in report.error
        assert not rec.ldr_path.is_file()
        assert not rec.render_path.is_file()

    @pytest.mark.parametrize(
        "exc", [TimeoutError("timed out"), RuntimeError("exited with code 1")]
    )
    def test_wraps_a_subprocess_failure(self, record, subprocess_raises, exc):
        # finalize turns either subprocess failure into a failed report
        subprocess_raises(exc)
        report = finalize(record)
        assert report.ok is False
        assert report.error is not None
        assert "Finalization failed" in report.error
        assert str(exc) in report.error
