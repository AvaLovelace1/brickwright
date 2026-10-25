"""Directed support through nearby surfaces that resist downward motion.

Contact uses separate surface proxies with the collision inset undone along each
triangle's normal. This leaves the collision tolerance unchanged. Surface normals
are oriented toward gravity or away from it, so open meshes and either winding
work without a volume or inside/outside test. Sliding and tipping are not checked.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

import fcl
import numpy as np

from ..ldraw.meshes import Mesh, quantization_bound
from .collision import (
    POSE_CACHE_SIZE,
    SURFACE_INSET_LDU,
    MeshBody,
    PartCollider,
    _candidate_pairs,
    _intersects,
    _world_bounds,
    build_collider,
    pose_resting,
    relative_pose,
)

# LDraw's vertical axis points down. Nearly vertical surfaces cannot establish
# support: the angular threshold rejects small normal errors from quantization.
_UP = np.array([0.0, -1.0, 0.0])
_MIN_UPWARD_NORMAL = 0.01
_NUMERIC_TOLERANCE = 1e-6
# Undoing the inset per triangle leaves small seams at faceted curves, such as
# the bottom of a roller skate. This 0.008 mm allowance is contact-only.
CONTACT_RECONSTRUCTION_LDU = 0.02


def supporting_pairs(
    bodies: Sequence[MeshBody], *, groups: Sequence[int] | None = None
) -> list[tuple[int, int]]:
    """Directed ``(supporter, supported)`` indices for actual surface contacts.

    ``groups`` optionally excludes pairs already joined by connectors. A contact
    can occur anywhere on a part, including a bracket's elevated ledge. Bodies
    that interpenetrate do not establish resting support with each other.
    """
    if len(bodies) < 2:
        return []
    lo, hi = _world_bounds(bodies)
    margins = (
        np.array(
            [SURFACE_INSET_LDU + quantization_bound(b.collider.mesh) for b in bodies]
        )[:, None]
        + CONTACT_RECONSTRUCTION_LDU
    )
    pairs = []
    for i, j in sorted(_candidate_pairs(lo - margins, hi + margins)):
        if groups is not None and groups[i] == groups[j]:
            continue
        a, b = bodies[i], bodies[j]
        forward, backward = _contacts(a, b), _contacts(b, a)
        if (forward or backward) and not _intersects(a, b):
            if forward:
                pairs.append((i, j))
            if backward:
                pairs.append((j, i))
    return sorted(pairs)


def _contacts(a: MeshBody, b: MeshBody) -> bool:
    local_up = tuple(np.round(a.rotation.T @ _UP, 8))
    other_up = tuple(np.round(b.rotation.T @ _UP, 8))
    return _relative_contact(
        a.collider, b.collider, local_up, other_up, relative_pose(a, b)
    )


@lru_cache(maxsize=POSE_CACHE_SIZE)
def _relative_contact(
    a: PartCollider,
    b: PartCollider,
    up_a: tuple[float, ...],
    up_b: tuple[float, ...],
    pose: bytes,
) -> bool:
    top = _surfaces(a, up_a)[0]
    bottom = _surfaces(b, up_b)[1]
    if top is None or bottom is None:
        return False
    pose_resting(bottom, pose)
    distance = fcl.distance(
        top.static, bottom.resting, fcl.DistanceRequest(), fcl.DistanceResult()
    )
    tolerance = (
        quantization_bound(a.mesh)
        + quantization_bound(b.mesh)
        + CONTACT_RECONSTRUCTION_LDU
    )
    return distance <= tolerance


@lru_cache(maxsize=1024)
def _surfaces(
    collider: PartCollider, up: tuple[float, ...]
) -> tuple[PartCollider | None, PartCollider | None]:
    triangles = collider.mesh.vertices[collider.mesh.faces]
    normals = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    lengths = np.linalg.norm(normals, axis=1)
    usable = lengths > _NUMERIC_TOLERANCE
    triangles, normals, lengths = triangles[usable], normals[usable], lengths[usable]
    normals = normals / lengths[:, None]
    vertical = normals @ np.asarray(up)
    usable = np.abs(vertical) > _MIN_UPWARD_NORMAL
    triangles, normals, vertical = triangles[usable], normals[usable], vertical[usable]
    if not len(triangles):
        return None, None
    normals *= np.where(vertical > 0, 1, -1)[:, None]
    offset = SURFACE_INSET_LDU * normals[:, None, :]
    faces = np.arange(3 * len(triangles), dtype=np.int32).reshape(-1, 3)
    return (
        build_collider(Mesh((triangles + offset).reshape(-1, 3), faces)),
        build_collider(Mesh((triangles - offset).reshape(-1, 3), faces)),
    )
