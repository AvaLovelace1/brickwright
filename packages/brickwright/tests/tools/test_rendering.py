"""Tests for rendering."""

import json
import os
from pathlib import Path

import ldraw2mesh.library
import pytest
from bricklayer import Color, LegoBuild, Position, Rotation, brick, flatten, to_ldraw
from ldraw2mesh.library import LDrawLibraryNotFound

from brickwright.tools.rendering import (
    build_ldraw,
    build_mesh,
    render,
    render_angle,
    render_available,
    render_views,
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def diagnostics_model():
    submodel = LegoBuild()
    submodel.add(brick(2, 1, color=Color.BLUE))
    model = LegoBuild()
    model.add(submodel)
    model.add(submodel, position=Position(4, 0, 3), rotation=Rotation.DEG_90)
    model.add(submodel, position=Position(8, 0, 3))
    model.add(submodel, position=Position(8, 0, 3))
    return model


def test_diagnostics_colors_each_instance_without_changing_geometry(
    record, diagnostics_model, monkeypatch
):
    from brickwright.tools import build_execution

    model = diagnostics_model
    original = to_ldraw(model)
    monkeypatch.setattr(build_execution, "create_build", lambda path: model)

    assert build_ldraw(record) == record.ldr_path
    inspected = (record.out_dir / "diagnostics" / "build.ldr").read_text()
    lines = [line.split() for line in inspected.splitlines() if line.startswith("1 ")]
    assert [int(line[1]) for line in lines] == [47, 14, 4, 4]
    source_lines = [line.split() for line in to_ldraw(flatten(model)).splitlines()]
    assert [line[2:] for line in lines] == [line[2:] for line in source_lines]
    assert record.ldr_path.read_text() == original
    assert to_ldraw(model) == original


@pytest.mark.parametrize("model_source", ["valid_build", "floating_build"])
def test_diagnostics_is_refreshed_without_leaving_a_stale_mesh(
    make_record, request, model_source
):
    rec = make_record(request.getfixturevalue("floating_build"))
    build_ldraw(rec)
    diagnostics_dir = rec.out_dir / "diagnostics"
    mesh = diagnostics_dir / "build.glb"
    mesh.write_bytes(b"old mesh")
    rec.write_build(request.getfixturevalue(model_source))
    build_ldraw(rec)
    lines = (diagnostics_dir / "build.ldr").read_text().splitlines()
    colors = [int(line.split()[1]) for line in lines if line.startswith("1 ")]
    assert colors == ([47] if model_source == "valid_build" else [47, 14])
    assert not mesh.exists()


@pytest.mark.parametrize("operation", [render, render_views, render_angle])
def test_render_exports_original_and_both_diagnostic_meshes(
    operation, make_record, valid_build, fake_render_pipeline, in_process, monkeypatch
):
    from brickwright.tools import rendering

    converted = []

    def convert(ldr, glb):
        assert ldr.is_file()
        glb.write_bytes(b"mesh")
        converted.append((ldr, glb))

    monkeypatch.setattr(rendering, "_convert", convert)
    monkeypatch.setattr(rendering, "_convert_connectivity", convert)
    rec = make_record(valid_build)
    args = (30, 15) if operation is render_angle else ()
    report = operation(rec, *args)
    assert report.ok, report.error
    diagnostics_dir = rec.out_dir / "diagnostics"
    assert converted == [
        (rec.ldr_path, rec.mesh_path),
        (diagnostics_dir / "build.ldr", diagnostics_dir / "build.glb"),
        (rec.connectivity_ldr_path, rec.connectivity_mesh_path),
    ]


def test_connectivity_export_is_refreshed_and_cleared_with_model_edits(
    make_record, valid_build, floating_build
):
    record = make_record(valid_build)
    build_ldraw(record)
    assert record.connectivity_ldr_path.is_file()
    assert (
        json.loads(record.connectivity_report_path.read_text())["component_count"] == 1
    )
    record.connectivity_mesh_path.write_bytes(b"stale")
    build_ldraw(record)
    assert not record.connectivity_mesh_path.exists()
    record.write_build(floating_build)
    assert not record.connectivity_ldr_path.exists()
    assert not record.connectivity_report_path.exists()


@pytest.fixture
def cruise_ship_model():
    """Source for a realistic multipart model."""
    return (_FIXTURES_DIR / "cruise_ship.py").read_text()


class TestRenderAvailable:
    def test_false_when_no_library_is_found(self, monkeypatch):
        def _raise():
            raise LDrawLibraryNotFound("nope")

        monkeypatch.setattr(ldraw2mesh.library, "resolve_library", _raise)
        assert render_available() is False

    def test_true_when_a_library_resolves(self, monkeypatch):
        monkeypatch.setattr(ldraw2mesh.library, "resolve_library", lambda: Path("/lib"))
        assert render_available() is True


class TestRender:
    def test_writes_a_png(
        self, make_record, valid_build, fake_render_pipeline, in_process
    ):
        # The builder's render writes only the combined contact sheet (one image).
        rec = make_record(valid_build)
        report = render(rec)
        assert report.ok is True
        assert report.image_path == rec.render_path
        assert rec.render_path.is_file()
        assert rec.render_path.stat().st_size > 0
        # No per-view files: those are written only by render_views() for the critic.
        assert not any(path.exists() for _, path in rec.render_views())

    def test_render_views_writes_each_view_separately(
        self, make_record, valid_build, fake_render_pipeline, in_process
    ):
        # The critique loop's render writes each view on its own (what the critic is
        # shown) plus the contact sheet (kept for snapshots / human viewing).
        rec = make_record(valid_build)
        report = render_views(rec)
        assert report.ok is True
        assert report.image_path == rec.render_path
        assert rec.render_path.is_file() and rec.render_path.stat().st_size > 0
        view_paths = [path for _, path in rec.render_views()]
        assert len(view_paths) == 4
        assert all(p.is_file() and p.stat().st_size > 0 for p in view_paths)

    def test_render_angle_writes_a_single_view(
        self, make_record, valid_build, fake_render_pipeline, in_process
    ):
        # The viewpoint agent's render writes one image from a chosen angle.
        rec = make_record(valid_build)
        report = render_angle(rec, azimuth=30.0, elevation=15.0)
        assert report.ok is True
        assert report.image_path == rec.viewpoint_path
        assert rec.viewpoint_path.is_file() and rec.viewpoint_path.stat().st_size > 0

    def test_render_angle_honors_out_path(
        self, make_record, valid_build, fake_render_pipeline, in_process
    ):
        # A caller can direct the render to a specific path (kept per candidate).
        rec = make_record(valid_build)
        dest = rec.path / "viewpoints" / "candidate.png"
        report = render_angle(rec, 10.0, 5.0, out_path=dest)
        assert report.ok is True
        assert report.image_path == dest
        assert dest.is_file() and dest.stat().st_size > 0
        assert not rec.viewpoint_path.exists()  # wrote only to out_path

    def test_build_error_is_reported(
        self, make_record, raising_build, fake_render_pipeline, in_process
    ):
        rec = make_record(raising_build)
        report = render(rec)
        assert report.ok is False
        assert report.error is not None
        assert "RuntimeError" in report.error
        assert "boom" in report.error

    @pytest.mark.parametrize(
        "exc", [TimeoutError("timed out"), RuntimeError("exited with code 1")]
    )
    def test_wraps_a_subprocess_failure(self, record, subprocess_raises, exc):
        subprocess_raises(exc)
        report = render(record)
        assert report.ok is False
        assert report.error is not None
        assert "Render failed" in report.error
        assert str(exc) in report.error


class TestRenderViews:
    _HAS_LDRAW_LIBRARY = bool(os.environ.get("LDRAW_LIBRARY_PATH"))
    skip_reason = "needs LDRAW_LIBRARY_PATH set"

    @pytest.mark.integration
    @pytest.mark.skipif(not _HAS_LDRAW_LIBRARY, reason=skip_reason)
    def test_diagnostics_glb_preserves_transparency_and_error_colors(
        self, record, diagnostics_model, monkeypatch
    ):
        from brickwright.tools import build_execution

        monkeypatch.setattr(
            build_execution, "create_build", lambda path: diagnostics_model
        )
        build_mesh(record)
        data = (record.out_dir / "diagnostics" / "build.glb").read_bytes()
        assert data[:4] == b"glTF" and data[16:20] == b"JSON"
        gltf = json.loads(data[20 : 20 + int.from_bytes(data[12:16], "little")])
        assert sum("mesh" in node for node in gltf["nodes"]) == 4
        materials = gltf["materials"]
        assert len(materials) == 3
        transparent = [mat for mat in materials if mat["alphaMode"] == "BLEND"]
        assert len(transparent) == 1
        colors = [mat["pbrMetallicRoughness"]["baseColorFactor"] for mat in transparent]
        assert all(0 < a < 1 for r, g, b, a in colors)
        opaque = [mat for mat in materials if mat["alphaMode"] == "OPAQUE"]
        assert len(opaque) == 2
        colors = [mat["pbrMetallicRoughness"]["baseColorFactor"] for mat in opaque]
        assert all(a == 1 for r, g, b, a in colors)
        assert any(r > g and r > b for r, g, b, a in colors)
        assert any(r > b and g > b and g > 0.5 for r, g, b, a in colors)

    @pytest.mark.integration
    @pytest.mark.skipif(not _HAS_LDRAW_LIBRARY, reason=skip_reason)
    def test_renders_a_real_model_to_a_png(
        self, make_record, cruise_ship_model, image_regression
    ):
        """Verifies the real rendering pipeline against a stored baseline image."""
        rec = make_record(cruise_ship_model)
        report = render(rec)
        assert report.ok is True, report.error
        image_regression.check(rec.render_path.read_bytes(), diff_threshold=1.0)
