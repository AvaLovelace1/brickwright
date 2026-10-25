"""Tests for mesh collision between placed parts."""

import numpy as np
import pytest

from bricklayer import PLATE, Color, LegoBuild, Pose, Position, brick, plate
from bricklayer.geometry.collision import (
    MATING_CLEARANCE_LDU,
    MeshBody,
    build_collider,
    colliding_pairs,
)
from bricklayer.ldraw.meshes import Mesh

IDENTITY = np.eye(3)


@pytest.fixture
def cubes(cube_mesh):
    """A body factory: one shared 10-LDU cube collider, posed at each translation."""
    collider = build_collider(cube_mesh(10))

    def _fn(*translations) -> list[MeshBody]:
        return [
            MeshBody(collider, IDENTITY, np.asarray(t, dtype=float))
            for t in translations
        ]

    return _fn


class TestBuildCollider:
    def test_records_the_local_bounding_box(self, cube_mesh):
        collider = build_collider(cube_mesh(10))
        assert collider.lo.tolist() == [-5, -5, -5]
        assert collider.hi.tolist() == [5, 5, 5]

    def test_an_empty_mesh_gets_zero_bounds(self):
        empty = Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int32))
        collider = build_collider(empty)
        assert collider.lo.tolist() == [0, 0, 0]
        assert collider.hi.tolist() == [0, 0, 0]


class TestCollidingPairs:
    def test_separated_bodies_do_not_collide(self, cubes):
        assert colliding_pairs(cubes((0, 0, 0), (100, 0, 0))) == []

    def test_interpenetrating_bodies_collide(self, cubes):
        assert colliding_pairs(cubes((0, 0, 0), (5, 0, 0))) == [(0, 1)]

    def test_seated_bodies_do_not_collide(self, cubes):
        """The inset leaves mating parts MATING_CLEARANCE_LDU apart, so seated
        parts clear rather than touch exactly."""
        offset = 10 + MATING_CLEARANCE_LDU
        assert colliding_pairs(cubes((0, 0, 0), (offset, 0, 0))) == []

    def test_deep_overlap_collides_despite_coplanar_faces(self, cubes):
        """Overlapping along y forces the sweep onto a different axis than usual,
        while the pair still shares coplanar side faces perpendicular to the
        overlap -- the first contact fcl reports there has zero depth even
        though the bodies deeply interpenetrate."""
        assert colliding_pairs(cubes((0, 0, 0), (0, 5, 0))) == [(0, 1)]

    def test_reports_every_colliding_pair(self, cubes):
        assert colliding_pairs(cubes((0, 0, 0), (4, 0, 0), (8, 0, 0))) == [
            (0, 1),
            (0, 2),
            (1, 2),
        ]

    def test_pairs_are_sorted_and_deduplicated(self, cubes):
        bodies = cubes((0, 0, 0), (4, 0, 0), (200, 0, 0), (203, 0, 0))
        assert colliding_pairs(bodies) == [(0, 1), (2, 3)]

    def test_no_bodies_gives_no_pairs(self):
        assert colliding_pairs([]) == []

    def test_one_body_cannot_collide(self, cubes):
        assert colliding_pairs(cubes((0, 0, 0))) == []

    def test_result_is_invariant_under_a_global_translation(self, cubes):
        near = colliding_pairs(cubes((0, 0, 0), (4, 0, 0), (100, 0, 0)))
        far = colliding_pairs(
            cubes((5000, -300, 20), (5004, -300, 20), (5100, -300, 20))
        )
        assert near == far

    def test_scales_past_the_broad_phase_sweep(self, cubes):
        """A grid seats many bodies at identical sweep-axis intervals, so the sweep
        admits them as candidates and only the perpendicular checks reject them.
        The one deliberately overlapped pair must still survive to the narrow phase."""
        grid = [(10.5 * x, 10.5 * y, 0.0) for x in range(20) for y in range(20)]
        bodies = cubes(*grid, (10.5 * 19 + 5, 10.5 * 19, 0.0))
        assert colliding_pairs(bodies) == [(399, 400)]

    def test_rotation_is_applied(self, cube_mesh):
        """A 45-degree turn widens a cube's diagonal enough to reach a neighbor
        that clears it when both are axis-aligned."""
        collider = build_collider(cube_mesh(10))
        angle = np.pi / 4
        turn = np.array(
            [
                [np.cos(angle), -np.sin(angle), 0],
                [np.sin(angle), np.cos(angle), 0],
                [0, 0, 1],
            ]
        )
        gap = np.array([10.5, 0.0, 0.0])
        assert (
            colliding_pairs(
                [
                    MeshBody(collider, IDENTITY, np.zeros(3)),
                    MeshBody(collider, IDENTITY, gap),
                ]
            )
            == []
        )
        assert colliding_pairs(
            [
                MeshBody(collider, turn, np.zeros(3)),
                MeshBody(collider, IDENTITY, gap),
            ]
        ) == [(0, 1)]


def model(*placements):
    """A model with each ``(element, position)`` placed by raw pose."""
    m = LegoBuild()
    for element, position in placements:
        m.add_raw(element, Pose(translation=position))
    return m


@pytest.fixture
def red_brick():
    return lambda: brick(4, 2, color=Color.RED)


class TestSeating:
    def test_exactly_stacked_bricks_do_not_collide(self, red_brick):
        m = model((red_brick(), Position(0, 0, 0)), (red_brick(), Position(0, 0, 1)))
        assert m.colliding_placements == ()

    def test_a_brick_sunk_one_plate_collides(self, red_brick):
        m = model(
            (red_brick(), Position(0, 0, 0)),
            (red_brick(), Position(0, 0, 1 - PLATE)),
        )
        assert len(m.colliding_placements) == 1

    def test_side_by_side_bricks_do_not_collide(self, red_brick):
        m = model((red_brick(), Position(0, 0, 0)), (red_brick(), Position(4, 0, 0)))
        assert m.colliding_placements == ()

    def test_overlapping_bricks_collide(self, red_brick):
        m = model((red_brick(), Position(0, 0, 0)), (red_brick(), Position(2, 0, 0)))
        assert len(m.colliding_placements) == 1

    def test_a_plate_seats_on_a_brick(self):
        m = model(
            (brick(4, 2, color=Color.RED), Position(0, 0, 0)),
            (plate(4, 2, color=Color.BLUE), Position(0, 0, 1)),
        )
        assert m.colliding_placements == ()

    def test_three_plates_stack_to_one_brick_height(self):
        m = model(
            *[
                (plate(2, 2, color=Color.WHITE), Position(0, 0, i * PLATE))
                for i in range(3)
            ]
        )
        assert m.colliding_placements == ()

    def test_coincident_bricks_collide(self, red_brick):
        m = model((red_brick(), Position(0, 0, 0)), (red_brick(), Position(0, 0, 0)))
        assert len(m.colliding_placements) == 1


class TestScale:
    def test_a_clean_wall_has_no_collisions(self):
        """Running bond: every other course offset by two studs."""
        m = LegoBuild()
        for row in range(10):
            for col in range(10):
                m.add_raw(
                    brick(4, 2, color=Color.WHITE),
                    Pose(translation=Position(4 * col + (2 if row % 2 else 0), 0, row)),
                )
        assert m.colliding_placements == ()
