"""Placements: an Element or a sub-LegoBuild posed in a model."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Generic, TypeVar

from .._mixins import Cached
from ..geometry import (
    Anchor,
    Connector,
    Cuboid,
    LegoGeometry,
    Mat3,
    Mounting,
    Pose,
    Position,
    Rotation,
)
from ..geometry.collision import MeshBody
from ..geometry.connections import (
    fit_mounting,
    mate_pose,
    mating_rule,
    mounting_pose,
)
from ..geometry.linalg import vec_max, vec_min
from ..geometry.spatial import as_position, require_grid_position
from ..ldraw.conversion import pose_to_ldraw
from ..ldraw.partdata import record
from ..parts.element import Element

if TYPE_CHECKING:
    from .build import LegoBuild


#: What a placement holds. Covariant: a placement is immutable, so a
#: ``Placement[Element]`` is usable wherever a plain ``Placement`` is. An
#: unparameterized ``Placement`` holds anything within the bound.
ContentT_co = TypeVar("ContentT_co", bound=LegoGeometry, covariant=True)

#: For :meth:`Placement.at`, which takes its content as an input (a covariant
#: parameter cannot appear in an input position).
_AtContentT = TypeVar("_AtContentT", bound=LegoGeometry)


@dataclass(frozen=True, eq=False)
class Placement(Cached, LegoGeometry, Generic[ContentT_co]):
    """An element or sub-model placed in a containing model.

    `content` and `pose` are fixed. Geometry is expressed in the containing model's
    frame and updates if the content is a mutable sub-model. Placements compare by
    identity; two placements can hold identical elements at different positions.
    """

    content: ContentT_co = field(
        metadata={"doc": "The element or sub-assembly placed."}
    )
    pose: Pose = field(
        default=Pose.IDENTITY,
        metadata={"doc": "Maps the content's local frame into the model's."},
    )

    def __post_init__(self) -> None:
        # Only a placed model can change, so only it needs a link.
        if isinstance(self.content, Cached):
            self._depends_on(self.content)

    @classmethod
    def at(
        cls,
        content: _AtContentT,
        position: Position | tuple[float, float, float] = Position.ZERO,
        rotation: Rotation = Rotation.DEG_0,
    ) -> Placement[_AtContentT]:
        """Place ``content`` with its rotated alignment box's min corner at ``position``.

        Grid-placement semantics: the content spins about its own origin, then
        re-anchors so the rotated alignment box's min corner sits at
        ``position``.
        """
        position = as_position(position)
        corner = rotated_alignment_corner(content, rotation)
        return Placement(content, Pose(rotation.matrix, position - corner))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.content!r}; {self.pose!r})"

    def transformed(self, pose: Pose) -> Placement[ContentT_co]:
        """The same content, re-posed by ``pose`` applied after this placement's."""
        return Placement(self.content, pose.compose(self.pose))

    @cached_property
    def collision_body(self) -> MeshBody:
        """This leaf's collision mesh, posed in world LDraw coordinates.

        Defined only for a placed :class:`Element`; flatten a model first.
        """
        if not isinstance(self.content, Element):
            raise TypeError(
                "collision_body is only defined for a placed Element;"
                " flatten the model first"
            )
        part = record(self.content.ldraw_id)
        rotation, translation = pose_to_ldraw(part.ldraw_pose(self.pose))
        return MeshBody(part.collider, rotation, translation)

    @cached_property
    def connectors(self) -> frozenset[Connector]:
        """The content's connector points, in world coordinates."""
        return frozenset(c.transformed(self.pose) for c in self.content.connectors)

    @cached_property
    def bounding_box(self) -> tuple[Position, Position]:
        """The content's physical bounding box, in world coordinates."""
        lo, hi = self.content.bounding_box
        if self.pose.is_grid_preserving:
            corners = (self.pose.apply(lo), self.pose.apply(hi))
            return vec_min(corners), vec_max(corners)
        return Cuboid.spanning(lo, hi).transformed(self.pose).aabb

    def to_world(self, p: Position | tuple[float, float, float]) -> Position:
        """Map a position from the content's local frame to world coordinates."""
        return self.pose.apply(as_position(p))


def rotated_alignment_corner(geometry: LegoGeometry, rotation: Rotation) -> Position:
    """The min corner of ``geometry``'s alignment box once ``rotation`` is applied.

    Rotating a box about the origin moves its min corner. Grid placement
    re-anchors by this vector, so the rotated alignment box's min corner lands
    exactly at the target position -- see :meth:`Placement.at`.
    """
    lo, hi = geometry.alignment_box
    return vec_min((rotation.rotate(lo), rotation.rotate(hi)))


def grid_placement(
    content: Element | LegoBuild,
    *,
    reference: Placement | None = None,
    offset: Position | tuple[float, float, float] = Position.ZERO,
    rotation: Rotation = Rotation.DEG_0,
    anchor: Anchor = Anchor.FRONT_RIGHT,
    target_anchor: Anchor = Anchor.FRONT_RIGHT,
    stacked: bool = False,
) -> Placement:
    """``content`` placed on the build grid, absolutely or relative to ``reference``.

    ``offset`` is an absolute grid position when ``reference`` is ``None``, and a
    delta from the reference otherwise. ``anchor`` pins a point on ``content``'s
    rotated footprint to the resolved position; ``target_anchor`` selects the
    point on the reference's rotated footprint the delta is measured from. With
    ``stacked``, the delta starts at the top of the reference's alignment box.

    Raises:
        ValueError: if ``offset`` is not on the integer build grid (x/y in whole
            studs, z in plates).
    """
    offset = require_grid_position(offset)
    position = _grid_position(reference, offset, target_anchor, stacked)
    ox, oy = anchor.offset(*content.rotated_footprint(rotation))
    return Placement.at(content, position - Position(ox, oy, 0), rotation)


def connect_placement(
    content: Element | LegoBuild,
    *,
    connector: Connector,
    to: Connector,
    mounting: Mounting | None = None,
    target_rotation: Mat3 | Rotation | None = None,
    target_position: Position | tuple[float, float, float] | None = None,
) -> Placement:
    """``content`` posed so its local ``connector`` mates the world-frame ``to``.

    By default the two connector points coincide with their frames aligned: the
    rest pose. ``target_rotation`` requests a final content rotation, while
    ``target_position`` requests a final world position for its connector.
    Omitted targets retain their rest values. The joint is fitted within its
    degrees of freedom, then any explicit ``mounting`` is applied.

    Raises:
        ValueError: if the two connectors cannot mate, or ``mounting`` does
            not fit the joint.
    """
    rule = mating_rule(connector.type, to.type)
    if rule is None:
        raise ValueError(f"{connector.type.name} and {to.type.name} cannot mate")
    pose = mate_pose(connector, to)
    if target_rotation is not None or target_position is not None:
        rotation = (
            target_rotation.matrix
            if isinstance(target_rotation, Rotation)
            else target_rotation
        )
        fitted = fit_mounting(
            rule.joint,
            connector,
            to,
            pose,
            target_rotation=pose.rotation if rotation is None else rotation,
            target_position=to.position
            if target_position is None
            else as_position(target_position),
        )
        pose = mounting_pose(fitted, to, rule.joint).compose(pose)
    if mounting is not None:
        pose = mounting_pose(mounting, to, rule.joint).compose(pose)
    return Placement(content, pose)


def leaf_paths(placements: Iterable[Placement]) -> Iterator[tuple[Placement, ...]]:
    """Each element occurrence's path through a sequence of placements."""
    for placement in placements:
        if isinstance(placement.content, Element):
            yield (placement,)
        else:
            for path in leaf_paths(placement.content.placements):
                yield (placement, *path)


def path_pose(path: Iterable[Placement]) -> Pose:
    """Compose a placement path into its containing model's frame."""
    pose = Pose.IDENTITY
    for placement in path:
        pose = pose.compose(placement.pose)
    return pose


def _grid_position(
    reference: Placement | None,
    offset: Position,
    target_anchor: Anchor,
    stacked: bool,
) -> Position:
    """Where a grid placement resolves to, before its own anchor is applied."""
    if reference is None:
        return offset
    content = reference.content
    rotation = Rotation.from_matrix(reference.pose.rotation)
    ax, ay = target_anchor.offset(*content.rotated_footprint(rotation))
    delta = offset + Position(ax, ay, 0)
    if stacked:
        delta += Position(0, 0, content.alignment_height)
    return (
        reference.pose.translation + rotated_alignment_corner(content, rotation) + delta
    )
