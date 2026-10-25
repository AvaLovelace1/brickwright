"""Directional surface support, independent of connectors and mesh closure."""

import numpy as np
import pytest

from bricklayer import from_ldraw
from bricklayer.geometry.collision import MeshBody, build_collider
from bricklayer.geometry.support import supporting_pairs
from bricklayer.ldraw.meshes import Mesh


def body(mesh, translation=(0, 0, 0), rotation=None):
    return MeshBody(
        build_collider(mesh),
        np.eye(3) if rotation is None else rotation,
        np.asarray(translation, dtype=float),
    )


def surface(vertices):
    return Mesh(np.asarray(vertices, dtype=float), np.array([[0, 1, 2], [0, 2, 3]]))


def test_seated_cube_has_only_upward_support(cube_mesh):
    cube = cube_mesh(10)
    assert supporting_pairs([body(cube), body(cube, (0, -10.5, 0))]) == [(0, 1)]


def test_side_contact_does_not_support(cube_mesh):
    cube = cube_mesh(10)
    assert supporting_pairs([body(cube), body(cube, (10.5, 0, 0))]) == []


@pytest.mark.parametrize("gap", [0.05, 0.25, 8])
def test_gap_beyond_inset_clearance_does_not_support(cube_mesh, gap):
    cube = cube_mesh(10)
    assert supporting_pairs([body(cube), body(cube, (0, -10.5 - gap, 0))]) == []


def test_interpenetration_is_not_resting_contact(cube_mesh):
    cube = cube_mesh(10)
    assert supporting_pairs([body(cube), body(cube, (0, -9.8, 0))]) == []


@pytest.mark.parametrize("reverse", [False, True])
def test_open_sloped_surfaces_support_without_friction(reverse):
    mesh = surface([[-5, 5, -5], [5, -5, -5], [5, -5, 5], [-5, 5, 5]])
    upper = Mesh(mesh.vertices, mesh.faces[:, ::-1]) if reverse else mesh
    normal = np.array([-1, -1, 0]) / np.sqrt(2)
    assert supporting_pairs([body(mesh), body(upper, normal * 0.5)]) == [(0, 1)]


def test_bracket_can_rest_on_an_elevated_ledge(cube_mesh):
    ledge = surface([[-1, -10, -5], [10, -10, -5], [10, -10, 5], [-1, -10, 5]])
    leg = surface([[-1, -10, -5], [-1, 10, -5], [-1, 10, 5], [-1, -10, 5]])
    bracket = Mesh(
        np.concatenate([ledge.vertices, leg.vertices]),
        np.concatenate([ledge.faces, leg.faces + 4]),
    )
    assert supporting_pairs([body(cube_mesh(10), (5, -4.5, 0)), body(bracket)]) == [
        (0, 1)
    ]


def test_rotated_faces_use_world_gravity(cube_mesh):
    cube = cube_mesh(10)
    angle = np.pi / 4
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0],
            [np.sin(angle), np.cos(angle), 0],
            [0, 0, 1],
        ]
    )
    offset = rotation @ np.array([0, -10.5, 0])
    assert supporting_pairs(
        [body(cube, rotation=rotation), body(cube, offset, rotation)]
    ) == [(0, 1)]


def test_global_rotation_changes_support_even_with_identical_relative_pose(cube_mesh):
    cube = cube_mesh(10)
    lower, upper = body(cube), body(cube, (0, -10.5, 0))
    assert supporting_pairs([lower, upper]) == [(0, 1)]
    rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    turned = [
        MeshBody(p.collider, rotation @ p.rotation, rotation @ p.translation)
        for p in (lower, upper)
    ]
    assert supporting_pairs(turned) == []


def test_overlapping_bounds_are_not_a_surface_contact():
    first = surface([[0, 0, 0], [10, -10, 0], [10, -10, 10], [0, 0, 10]])
    second = body(first, (0, -2, 0))
    assert supporting_pairs([body(first), second]) == []


def test_degenerate_triangles_are_ignored():
    mesh = Mesh(np.zeros((3, 3)), np.array([[0, 1, 2]]))
    assert supporting_pairs([body(mesh), body(mesh)]) == []


def test_small_side_offset_does_not_hide_top_contact(cube_mesh):
    cube = cube_mesh(10)
    assert supporting_pairs([body(cube), body(cube, (9, -10.5, 0))]) == [(0, 1)]


def test_empty_scene_and_empty_mesh_have_no_support():
    empty = Mesh(np.empty((0, 3)), np.empty((0, 3), dtype=int))
    assert supporting_pairs([]) == []
    assert supporting_pairs([body(empty), body(empty)]) == []


def test_spaceship_cone_overlapping_engine_bounds_still_has_no_contact():
    model = from_ldraw(
        "1 0 -58 -20 56 1 0 0 0 1 0 0 0 1 30358.dat\n"
        "1 71 -42 -25 108 1 0 0 0 0 -1 0 1 0 98100.dat\n"
    )
    assert supporting_pairs([p.collision_body for p in model.placements]) == []
