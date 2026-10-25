"""Mesh collision between placed parts.

Collision runs on BrickNet's inset meshes, in raw LDraw units; the inset
(:data:`SURFACE_INSET_LDU`) is the whole tolerance.

Bodies share one bounding-volume hierarchy per part and differ only by transform,
so a wall of a thousand identical bricks builds a single BVH.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import fcl
import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from ..ldraw.meshes import Mesh

# Every collision mesh is inset this far along each surface normal, so two mating
# parts sit MATING_CLEARANCE_LDU apart instead of exactly touching.
SURFACE_INSET_LDU = 0.25
MATING_CLEARANCE_LDU = 2 * SURFACE_INSET_LDU

# Relative poses are rounded to this many decimals (in LDU) before keying the narrow-phase cache.
_POSE_DIGITS = 6
POSE_CACHE_SIZE = 8192
_COLLISION_REQUEST = fcl.CollisionRequest(num_max_contacts=1, enable_contact=False)


@dataclass(frozen=True, eq=False)
class PartCollider:
    """One part's collision geometry, built once and shared by every placement.

    ``lo`` and ``hi`` are the mesh's own axis-aligned bounds in LDU, kept so the
    broad phase can bound a posed body without touching its vertices.

    ``static`` and ``resting`` are two fcl handles onto ``bvh``, built once per
    part since each costs time proportional to the triangle count. The narrow
    phase re-poses ``resting`` only; re-posing ``static`` would make fcl
    recompute the whole hierarchy's bounds.

    Compared by identity: a part's collider is a singleton, and the fields are
    numpy arrays that have no meaningful equality here.
    """

    bvh: Any
    lo: np.ndarray
    hi: np.ndarray
    static: Any
    resting: Any
    mesh: Mesh


@dataclass(frozen=True)
class MeshBody:
    """A :class:`PartCollider` posed in world space, in LDraw units."""

    collider: PartCollider
    rotation: np.ndarray
    translation: np.ndarray


def build_collider(mesh: Mesh) -> PartCollider:
    """A hierarchy over ``mesh``, ready to pose and collide."""
    vertices = np.ascontiguousarray(mesh.vertices, dtype=float)
    model = fcl.BVHModel()
    model.beginModel(len(vertices), len(mesh.faces))
    model.addSubModel(vertices, np.ascontiguousarray(mesh.faces, dtype=np.int32))
    model.endModel()
    return PartCollider(
        model,
        *mesh.bounds,
        fcl.CollisionObject(model, fcl.Transform()),
        fcl.CollisionObject(model, fcl.Transform()),
        mesh,
    )


def colliding_pairs(bodies: Sequence[MeshBody]) -> list[tuple[int, int]]:
    """Index pairs of ``bodies`` whose meshes interpenetrate, sorted.

    A sweep over world bounds culls the pairs; exact triangle intersection
    decides each survivor.
    """
    if len(bodies) < 2:
        return []
    lo, hi = _world_bounds(bodies)
    return [
        pair
        for pair in sorted(_candidate_pairs(lo, hi))
        if _intersects(bodies[pair[0]], bodies[pair[1]])
    ]


def _world_bounds(bodies: Sequence[MeshBody]) -> tuple[np.ndarray, np.ndarray]:
    """Each body's axis-aligned world bounds, in LDU.

    A rotated box's world half-width along an axis is ``sum_k half_k * |R_dk|``,
    so the bounds fall out of the rotation without transforming any corner.
    """
    count = len(bodies)
    rotations = np.empty((count, 3, 3))
    translations = np.empty((count, 3))
    local_lo = np.empty((count, 3))
    local_hi = np.empty((count, 3))
    for n, body in enumerate(bodies):
        rotations[n] = body.rotation
        translations[n] = body.translation
        local_lo[n] = body.collider.lo
        local_hi[n] = body.collider.hi
    half = (local_hi - local_lo) / 2
    centers = np.einsum("ndk,nk->nd", rotations, (local_lo + local_hi) / 2)
    centers += translations
    reach = np.einsum("ndk,nk->nd", np.abs(rotations), half)
    return centers - reach, centers + reach


def _candidate_pairs(lo: np.ndarray, hi: np.ndarray) -> Iterator[tuple[int, int]]:
    """Index pairs whose world bounds overlap, by sweeping the widest axis.

    Sorting by each body's low edge lets the sweep stop as soon as a neighbor
    starts past the current body's high edge. The sweep leaves only a handful of
    neighbors per body, so the remaining tests run on plain floats.
    """
    axis = int(np.argmax(hi.max(axis=0) - lo.min(axis=0)))
    first, second = (a for a in range(3) if a != axis)
    los, his = lo.tolist(), hi.tolist()
    order = sorted(range(len(los)), key=lambda n: los[n][axis])
    starts = [los[n][axis] for n in order]
    for k, i in enumerate(order):
        lo_i, hi_i = los[i], his[i]
        stop = bisect_right(starts, hi_i[axis])
        for j in order[k + 1 : stop]:
            lo_j, hi_j = los[j], his[j]
            if (
                lo_j[first] < hi_i[first]
                and lo_i[first] < hi_j[first]
                and lo_j[second] < hi_i[second]
                and lo_i[second] < hi_j[second]
            ):
                yield (i, j) if i < j else (j, i)


def _intersects(a: MeshBody, b: MeshBody) -> bool:
    """Whether two posed meshes share interior volume.

    Overlap depends only on how the two parts sit *relative* to each other, and a
    build repeats a handful of relative poses over and over -- every brick in a
    wall meets its neighbor the same way. Posing ``b`` in ``a``'s frame turns that
    repetition into cache hits on the one expensive step.
    """
    return _relative_intersects(a.collider, b.collider, relative_pose(a, b))


def relative_pose(a: MeshBody, b: MeshBody) -> bytes:
    """``b``'s pose in ``a``'s frame, rounded into one 12-float cache key.

    Nine floats hold the rotation and three the translation, so a single
    ``tobytes`` keys the narrow-phase caches.
    """
    pose = np.empty(12)
    pose[:9] = (a.rotation.T @ b.rotation).reshape(9)
    pose[9:] = a.rotation.T @ (b.translation - a.translation)
    return np.round(pose, _POSE_DIGITS).tobytes()


def pose_resting(collider: PartCollider, pose: bytes) -> None:
    """Move ``collider.resting`` to a pose from :func:`relative_pose`."""
    values = np.frombuffer(pose)
    collider.resting.setTransform(
        fcl.Transform(values[:9].reshape(3, 3).copy(), values[9:].copy())
    )


@lru_cache(maxsize=POSE_CACHE_SIZE)
def _relative_intersects(a: PartCollider, b: PartCollider, pose: bytes) -> bool:
    """Whether ``b``, posed by :func:`relative_pose`, overlaps ``a``.

    Colliders are per-part singletons, so they key the cache by identity.
    """
    pose_resting(b, pose)
    return bool(
        fcl.collide(a.static, b.resting, _COLLISION_REQUEST, fcl.CollisionResult())
    )
