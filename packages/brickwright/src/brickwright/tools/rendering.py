"""Create a record's build and render it to a multi-view PNG."""

from __future__ import annotations

import json
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from ..config import Config
from ..record import Record
from . import build_execution

# Camera semantics come from the CPU renderer, so the two pipelines' images agree.
from .software_rendering import (
    VIEW_DIRECTIONS,
    VIEW_ORDER,
    VIEW_UP_VECTORS,
    Vec3,
    angle_to_view_dir,
    angle_up,
    tile_images,
)

if TYPE_CHECKING:
    from bricklayer import LegoBuild

# The heavy render stack (pygfx, rendercanvas, PIL, ldraw2mesh) loads inside the
# functions that use it: each child process re-imports this module.


class RenderReport(BaseModel):
    """The result of rendering a build to an image."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    image_path: Path | None = None  # the written contact sheet, when ok
    error: str | None = None  # a clean message or a traceback when not ok


def render_available() -> bool:
    """Whether an LDraw parts library is available for rendering."""
    from ldraw2mesh.library import LDrawLibraryNotFound, resolve_library

    try:
        resolve_library()
    except LDrawLibraryNotFound:
        return False
    return True


def render(record: Record, config: Config | None = None) -> RenderReport:
    """Create the build and render the four views tiled into one contact sheet."""
    return _in_subprocess(_render, (record,), config)


def render_views(record: Record, config: Config | None = None) -> RenderReport:
    """Create the build and render each canonical view plus the contact sheet."""
    return _in_subprocess(_render_views, (record,), config)


def render_angle(
    record: Record,
    azimuth: float,
    elevation: float,
    config: Config | None = None,
    *,
    out_path: Path | None = None,
) -> RenderReport:
    """Create the build and render a single image from a spherical camera angle.

    ``azimuth`` and ``elevation`` are in degrees. The image is written to
    ``out_path`` when given, else to ``record.viewpoint_path``.
    """
    destination = out_path or record.viewpoint_path
    return _in_subprocess(
        _render_angle, (record, azimuth, elevation, destination), config
    )


def mesh2png(glb: Path, png: Path) -> None:
    """Save a multi-view contact sheet of an existing glTF mesh."""
    _save_png(tile_images(_view_arrays(glb)), png)


def build_ldraw(record: Record, build: LegoBuild | None = None) -> Path:
    """Export original, collision and connected-component LDraw files."""
    from bricklayer import write_ldraw

    from .connectivity_diagnostics import connectivity_diagnostic

    if build is None:
        build = build_execution.create_build(record.build_path)
    record.diagnostics_dir.mkdir(parents=True, exist_ok=True)
    record.diagnostics_mesh_path.unlink(missing_ok=True)
    write_ldraw(build, record.ldr_path)
    write_ldraw(_diagnostics_build(build), record.diagnostics_ldr_path)
    record.connectivity_dir.mkdir(parents=True, exist_ok=True)
    record.connectivity_mesh_path.unlink(missing_ok=True)
    diagnostic = connectivity_diagnostic(build)
    record.connectivity_ldr_path.write_text(diagnostic.ldraw)
    record.connectivity_report_path.write_text(
        json.dumps(diagnostic.metadata, indent=2) + "\n"
    )
    return record.ldr_path


def build_mesh(record: Record, build: LegoBuild | None = None) -> Path:
    """Export the original and both diagnostic views as LDraw and glTF."""
    _convert(build_ldraw(record, build), record.mesh_path)
    _convert(record.diagnostics_ldr_path, record.diagnostics_mesh_path)
    _convert_connectivity(record.connectivity_ldr_path, record.connectivity_mesh_path)
    return record.mesh_path


def _in_subprocess(
    fn: Callable[..., Path], args: tuple[Any, ...], config: Config | None
) -> RenderReport:
    """Run a render body in a child process under the render timeout."""
    config = config or Config()
    return build_execution.run_guarded(
        _reported,
        (fn, *args),
        config.render_timeout,
        lambda e: RenderReport(ok=False, error=f"Render failed: {e}"),
    )


def _reported(fn: Callable[..., Path], *args: Any) -> RenderReport:
    """Run a render body, reporting the image it wrote or its traceback."""
    try:
        return RenderReport(ok=True, image_path=fn(*args))
    except Exception:
        return RenderReport(ok=False, error=traceback.format_exc())


def _render(record: Record) -> Path:
    mesh2png(build_mesh(record), record.render_path)
    return record.render_path


def _render_views(record: Record) -> Path:
    views = _view_arrays(build_mesh(record))
    for (_, view_path), tile in zip(record.render_views(), views):
        _save_png(tile, view_path)
    _save_png(tile_images(views), record.render_path)
    return record.render_path


def _render_angle(
    record: Record, azimuth: float, elevation: float, out_path: Path
) -> Path:
    tile = _angle_array(
        build_mesh(record), angle_to_view_dir(azimuth, elevation), angle_up(elevation)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _save_png(tile, out_path)
    return out_path


def _diagnostics_build(build: LegoBuild) -> LegoBuild:
    """Red collisions override yellow floating parts; other parts are clear."""
    from bricklayer import Color, Element, LegoBuild, Placement

    colliding = {part for pair in build.colliding_placements for part in pair}
    floating = set(build.floating_placements)
    placements = []
    for placement in build.flattened_placements:
        if placement in colliding:
            color = Color.RED
        elif placement in floating:
            color = Color.YELLOW
        else:
            color = Color.TRANS_CLEAR
        placements.append(
            Placement(Element(placement.content.ldraw_id, color), placement.pose)
        )
    return LegoBuild(placements)


def _convert(ldr: Path, glb: Path) -> None:
    from ldraw2mesh import convert

    convert(ldr, glb, gaps=True)


def _convert_connectivity(ldr: Path, glb: Path) -> None:
    from .connectivity_diagnostics import convert_connectivity_diagnostics

    convert_connectivity_diagnostics(ldr, glb)


def _save_png(image: np.ndarray, path: Path) -> None:
    """Save an RGBA array as an RGB PNG."""
    from PIL import Image

    Image.fromarray(image, "RGBA").convert("RGB").save(path)


def _build_scene(glb_path: Path, size: int):
    """Load the glTF and set up the scene, camera, and canvas for rendering.

    Returns ``(model, camera, canvas)``; call ``camera.show_object(...)`` then
    ``canvas.draw()`` to render a view. A directional key light is parented to the
    camera so it follows whatever view is framed.
    """
    import pygfx as gfx
    from rendercanvas.offscreen import RenderCanvas

    model = gfx.load_gltf(str(glb_path)).scene

    scene = gfx.Scene()
    scene.add(gfx.AmbientLight(intensity=0.6))
    scene.add(model)

    canvas = RenderCanvas(size=(size, size), pixel_ratio=1)
    renderer = gfx.renderers.WgpuRenderer(canvas)
    camera = gfx.PerspectiveCamera(50)
    camera.add(gfx.DirectionalLight(intensity=2.5))  # key light follows the camera
    scene.add(camera)

    canvas.request_draw(lambda: renderer.render(scene, camera))
    return model, camera, canvas


def _view_arrays(glb_path: Path, *, size: int = 512) -> list[np.ndarray]:
    """Render one image per canonical view (as numpy arrays)."""
    model, camera, canvas = _build_scene(glb_path, size)
    out: list[np.ndarray] = []
    for name in VIEW_ORDER:
        camera.show_object(
            model, view_dir=VIEW_DIRECTIONS[name], up=VIEW_UP_VECTORS[name]
        )
        out.append(np.asarray(canvas.draw()))
    return out


def _angle_array(
    glb_path: Path, view_dir: Vec3, up: Vec3, *, size: int = 512
) -> np.ndarray:
    """Render a single view from an arbitrary camera direction (as a numpy array)."""
    model, camera, canvas = _build_scene(glb_path, size)
    camera.show_object(model, view_dir=view_dir, up=up)
    return np.asarray(canvas.draw())
