"""LegoBuild: a build assembled and edited in place."""

from __future__ import annotations

from bisect import insort
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from functools import cached_property
from itertools import pairwise
from typing import Any, TypeAlias, TypeVar, cast
from weakref import WeakKeyDictionary

from .._mixins import Cached
from ..geometry import (
    Anchor,
    Connector,
    ConnectorType,
    JointCoordinates,
    LegoGeometry,
    Mat3,
    Mounting,
    Pose,
    Position,
    Rotation,
)
from ..geometry.collision import colliding_pairs
from ..geometry.connections import Matings, mated, same_connector
from ..geometry.linalg import Scalar, format_scalar, vec_max, vec_min
from ..geometry.spatial import BUILD_TOLERANCE
from ..geometry.support import supporting_pairs
from ..parts.element import Element
from ._graph import component_roots
from .articulation import (
    Joint,
    MotionRange,
    MotionReport,
    check_motion,
    posed,
    prefixed,
    record_connection,
    remap_joint,
)
from .names import NameRegistry
from .placement import Placement, connect_placement, grid_placement, leaf_paths

#: The content type re-posed by :meth:`LegoBuild._compose`, shared between the
#: placement it is given and the placement it returns.
_ContentT = TypeVar("_ContentT", bound=LegoGeometry)
_MemoT = TypeVar("_MemoT")

#: A placement's name, or a path of names reaching into nested sub-models:
#: ``['A', 'B']`` is the placement named ``B`` in the sub-model placed as ``A``.
NameRef: TypeAlias = str | Sequence[str]


class LegoBuild(Cached, LegoGeometry):
    """A build or reusable sub-assembly, edited in place.

    Validity queries update automatically after edits, including edits to nested
    models. `is_valid` checks collisions and ground support; `is_connected` checks
    whether every part joins through compatible connectors.
    """

    def __init__(
        self,
        placements: Iterable[Placement] = (),
        names: Mapping[str, Placement] | None = None,
        steps: Iterable[int] | None = None,
        *,
        joints: Iterable[Joint] = (),
    ) -> None:
        self._placements: list[Placement] = []
        self._joints: list[Joint] = list(joints)
        self._reset_compose_cache()
        self._steps: list[int] = []
        for placement in placements:
            self._record(placement)
        self._names: NameRegistry[Placement] = NameRegistry(names)
        self._steps.extend(_validated_steps(steps or (), len(self._placements)))
        if self._joints:
            paths = set(leaf_paths(self._placements))
            if any(
                endpoint.path not in paths
                for joint in self._joints
                for endpoint in (joint.parent, joint.child)
            ):
                raise ValueError(
                    "joint endpoints must be leaf occurrences in this model"
                )

    def __getstate__(self) -> dict[str, Any]:
        """Pickled state without the weak composition cache."""
        return {
            key: value
            for key, value in super().__getstate__().items()
            if key != "_compose_cache"
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        super().__setstate__(state)
        self._reset_compose_cache()

    @cached_property
    def placements(self) -> tuple[Placement, ...]:
        """Every top-level placement in the model, in insertion order."""
        return tuple(self._placements)

    @property
    def names(self) -> Mapping[str, Placement]:
        """The model's named placements, keyed by the name each was registered under.

        A live read-only view: names appear as parts are added.
        """
        return self._names.as_mapping()

    @property
    def step_markers(self) -> tuple[int, ...]:
        """Where the model's build-step markers fall, as placement counts.

        Each entry is the number of placements ahead of that marker, so a
        marker at ``len(placements)`` closes the last step and a marker at 0
        closes an empty one ahead of the first placement. The sequence is
        non-decreasing, and repeats are allowed. :attr:`steps` reads the same
        markers as groups of placements; this is the exact record the LDraw
        writer replays.
        """
        return tuple(self._steps)

    @property
    def steps(self) -> tuple[tuple[Placement, ...], ...]:
        """Placements grouped into build steps.

        Each marker closes a group; any trailing placements form one more group.
        Repeated markers produce empty groups.
        """
        groups = []
        start = 0
        for marker in self._steps:
            groups.append(self.placements[start:marker])
            start = marker
        tail = self.placements[start:]
        if tail:
            groups.append(tail)
        return tuple(groups)

    def add(
        self,
        content: Element | LegoBuild,
        position: Position | tuple[float, float, float] = Position.ZERO,
        rotation: Rotation = Rotation.DEG_0,
        anchor: Anchor = Anchor.FRONT_RIGHT,
        *,
        relative_to: NameRef | Placement | None = None,
        target_anchor: Anchor = Anchor.FRONT_RIGHT,
        name: str | None = None,
        index: int | None = None,
    ) -> Placement:
        """Place content on the grid; return its placement.

        `position` is an absolute `(x, y, z)` or a delta from `relative_to` (a name,
        name path, or placement). `rotation` is the content's own rotation, not relative
        to the reference. Positions require integer x/y and z in whole plates.

        `anchor` selects the point on the content's rotated alignment footprint;
        `target_anchor` selects the reference point when using `relative_to`.
        The default is the front-right minimum corner. An even extent's center floors
        toward that corner: `Anchor.CENTER` on a 4x2 footprint is `(1, 0)` studs from it.

        `name` registers the result; `index` inserts instead of appending. Content is
        held by reference. A concrete reference is read in this model's frame, even
        if from another model or removed; it is not added automatically.

        Raises `ValueError` for off-grid positions, `KeyError` for missing names,
        and `IndexError` for an out-of-range insertion.
        """
        return self._add_grid(
            content,
            ref=relative_to,
            offset=position,
            rotation=rotation,
            anchor=anchor,
            target_anchor=target_anchor,
            name=name,
            index=index,
        )

    def remove(self, target: int | str | Placement) -> Placement:
        """Remove and return a top-level placement by index, name, or identity.

        Negative indices count from the end. Repeated placements lose their first
        occurrence; the name is freed after the last. Build steps track the removal.
        Nested name paths are not accepted: edit the sub-model itself, which affects
        all models sharing it. Missing indices/names raise `IndexError`/`KeyError`;
        unknown placements raise `ValueError` and unsupported target types `TypeError`.
        """
        if isinstance(target, bool):
            raise TypeError(
                f"remove takes a placement index, name, or Placement, not a bool: {target!r}"
            )
        elif isinstance(target, int):
            index = _normalized_index(target, len(self._placements))
        elif isinstance(target, str | Placement):
            placement = self._names[target] if isinstance(target, str) else target
            try:
                index = self._placements.index(placement)
            except ValueError:
                description = (
                    f"the part named {target!r}"
                    if isinstance(target, str)
                    else "target"
                )
                raise ValueError(
                    f"{description} is not a placement in this model"
                ) from None
        else:
            raise TypeError(
                "remove takes a placement index, name, or Placement; to remove a part "
                "from a sub-model, remove it from that sub-model directly"
            )
        placement = self._placements.pop(index)
        self._steps = [m - 1 if m > index else m for m in self._steps]
        if isinstance(placement.content, Cached):
            self._unlink(placement)
        # A model constructed with the same placement twice keeps it placed,
        # named, and composable until the last copy goes.
        if placement not in self._placements:
            self._names.unregister(placement)
            self._drop_composed(placement)
        self._invalidate()
        return placement

    def add_raw(
        self,
        content: Element | LegoBuild,
        pose: Pose = Pose.IDENTITY,
        *,
        name: str | None = None,
        index: int | None = None,
    ) -> Placement:
        """Place content at an arbitrary pose without grid checks or re-anchoring.

        `pose` maps the content's local frame into this model. An element's origin is
        its alignment box's bottom-center; a sub-model retains its own frame.
        Content is shared by reference. `name` registers the placement and `index`
        inserts instead of appending. Invalid insertion indices raise `IndexError`.
        """
        return self._place(Placement(content, pose), name, index)

    def stack(
        self,
        content: Element | LegoBuild,
        on: NameRef | Placement,
        offset: Position | tuple[float, float, float] = Position.ZERO,
        rotation: Rotation = Rotation.DEG_0,
        anchor: Anchor = Anchor.FRONT_RIGHT,
        target_anchor: Anchor = Anchor.FRONT_RIGHT,
        *,
        name: str | None = None,
        index: int | None = None,
    ) -> Placement:
        """Place content on top of `on` (a name, name path, or placement).

        The new part's alignment-box bottom rests at the reference's alignment-box top.
        `offset` shifts from there in studs/bricks and must be on the grid.
        Use `anchor=Anchor.CENTER, target_anchor=Anchor.CENTER` to center footprints;
        anchors, absolute rotation, shared content, naming, and insertion behave as in `add`.

        A concrete reference is read in this model's frame even if removed or from another
        model. Later changes to that reference do not move this placement.
        """
        return self._add_grid(
            content,
            ref=on,
            offset=offset,
            rotation=rotation,
            anchor=anchor,
            target_anchor=target_anchor,
            stacked=True,
            name=name,
            index=index,
        )

    def connect(
        self,
        content: Element | LegoBuild,
        connector: Connector | ConnectorType | str,
        to: Connector,
        *,
        mounting: Mounting | None = None,
        motion: MotionRange | None = None,
        target_rotation: Mat3 | Rotation | None = None,
        target_position: Position | tuple[float, float, float] | None = None,
        name: str | None = None,
        index: int | None = None,
    ) -> Placement:
        """Place content by mating a local connector to a world target.

        ``target_rotation`` and ``target_position`` fit the pose; ``mounting`` then
        adds clocking, insertion, flip, or ball swing. Motion is relative to this pose.

        A target in this model records a static joint. Set ``motion`` to a
        ``MotionRange`` matching the joint's ``kind`` to enable movement.

        Both connectors must identify unique leaf occurrences. A geometric
        target outside this model may still position static content, but cannot
        declare motion. No placement or joint is recorded if validation fails.
        """
        source = _resolve_connector(content, connector)
        placement = connect_placement(
            content,
            connector=source,
            to=to,
            mounting=mounting,
            target_rotation=target_rotation,
            target_position=target_position,
        )
        joint = record_connection(self, placement, source, to, motion)
        return self._place(placement, name, index, joint=joint)

    @property
    def joints(self) -> tuple[Joint, ...]:
        """Connections recorded in this model; nested records stay in their owner.

        Removing either endpoint, including a nested leaf, deletes its record.
        """
        return tuple(self._joints)

    @cached_property
    def flattened_joints(self) -> tuple[Joint, ...]:
        """All joint occurrences, with endpoint paths rooted in this model.

        A repeated sub-model contributes distinct records for each occurrence.
        Use these records as keys to ``posed`` when moving a nested joint.
        """
        return self.joints + tuple(
            self._compose_joint(p, joint)
            for p in self.placements
            if isinstance(p.content, LegoBuild)
            for joint in p.content.flattened_joints
        )

    def joint(self, child: Placement) -> Joint:
        """The locally recorded joint that placed ``child`` using ``connect``."""
        for joint in self._joints:
            if joint.child.path[0] is child:
                return joint
        raise ValueError("placement has no joint in this model")

    def set_motion(self, joint: Joint | Placement, motion: MotionRange | None) -> Joint:
        """Replace a local joint's range; ``None`` makes it static. Return the record."""
        if isinstance(joint, Placement):
            joint = self.joint(joint)
        if joint not in self._joints:
            raise ValueError("joint does not belong to this model")
        updated = joint.with_motion(motion)
        self._joints[self._joints.index(joint)] = updated
        self._invalidate()
        return updated

    def posed(self, positions: Mapping[Joint, JointCoordinates]) -> LegoBuild:
        """A flat geometry snapshot at joint coordinates, leaving this build intact.

        Keys come from ``joints`` or ``flattened_joints``. Unspecified positions
        stay at zero. Static connections and attached rigid assemblies follow
        the moving parts. The snapshot has no joint records; evaluate every
        pose from the original build. Closed motion loops raise ``ValueError``.
        """
        return posed(self, positions)

    def check_motion(
        self, *, samples: int = 5, max_samples: int = 10000
    ) -> MotionReport:
        """Optionally check collisions, floating, and engagement across joint ranges.

        Samples the Cartesian product, including zero and both limits on every
        coordinate. Unannotated connections remain rigid, which can flag motions
        possible with additional flexibility. A clear report covers only the samples.
        Exceeding the sample budget or encountering a motion loop raises.
        """
        return check_motion(self, samples=samples, max_samples=max_samples)

    def extend(
        self,
        other: LegoBuild,
        position: Position | tuple[float, float, float] = Position.ZERO,
        rotation: Rotation = Rotation.DEG_0,
        anchor: Anchor = Anchor.FRONT_RIGHT,
    ) -> tuple[Placement, ...]:
        """Splice `other`'s current top-level placements into this model.

        The resulting geometry matches `add(other, position, rotation, anchor)`, but
        without a wrapper sub-model or its names. Returns the new placements in order.
        Later additions to `other` do not carry over; nested content remains shared.
        Raises `ValueError` for off-grid positions or cyclic nesting.
        """
        outer = grid_placement(other, offset=position, rotation=rotation, anchor=anchor)
        composed = tuple(inner.transformed(outer.pose) for inner in other.placements)
        # All checked before any is recorded: recording never adds to this
        # model's own dependents, which is what `_check_placeable` walks.
        for placement in composed:
            self._check_placeable(placement.content)
        paths = dict(zip(leaf_paths(other.placements), leaf_paths(composed)))
        joints = tuple(remap_joint(j, paths) for j in other.joints)
        result = tuple(self._place(p) for p in composed)
        self._joints.extend(joints)
        self._invalidate()
        return result

    def add_step(self, index: int | None = None) -> None:
        """Close the build step before `index` placements, defaulting to all so far.

        Indices are placement counts; negative values count from the end. Steps are
        ordered by position. Repeated markers create empty steps, useful for a final
        instruction page. The LDraw writer emits one `0 STEP` per marker.
        Raises `IndexError` for an out-of-range index.
        """
        count = len(self._placements)
        marker = (
            count if index is None else _normalized_index(index, count, insert=True)
        )
        insort(self._steps, marker)

    def remove_step(self, index: int) -> None:
        """Drop one build-step marker sitting at ``index`` placements.

        ``index`` is a placement count, as in :meth:`add_step`. Markers are
        plain counts, so two markers at one count are indistinguishable and
        dropping either leaves the same model.

        Raises:
            IndexError: if ``index`` is outside the model's placements.
            ValueError: if no marker sits at that count.
        """
        marker = _normalized_index(index, len(self._placements), insert=True)
        try:
            self._steps.remove(marker)
        except ValueError:
            raise ValueError(
                f"no build-step marker at {marker} placements; "
                f"markers sit at {sorted(set(self._steps))}"
            ) from None

    def copy(self) -> LegoBuild:
        """A shallow copy holding the same placements under the same names.

        Placements and nested sub-models are shared. Build-step markers carry
        over. Adding to either outer model leaves the other alone; editing a
        shared sub-model affects both. Use :meth:`deepcopy` to isolate those edits.
        """
        return type(self)(
            self._placements, dict(self.names), self._steps, joints=self.joints
        )

    def deepcopy(self) -> LegoBuild:
        """Copy this model and nested sub-models, isolating subsequent edits.

        Names, poses, and build steps are preserved. Repeated sub-models stay shared
        within the copy, but no mutable content is shared with the original.
        """
        return deepcopy(self)

    def __repr__(self) -> str:
        n = self.brick_count
        unit = "brick" if n == 1 else "bricks"
        dims = "x".join(
            str(format_scalar(round(d, 3)))
            for d in (self.width, self.depth, self.height)
        )
        return f"{type(self).__name__}({n} {unit}, {dims})"

    def named(self, name: NameRef) -> Placement:
        """Look up a name or nested path such as `['tower', 'roof']`.

        Returns a placement in this model's frame, suitable for `relative_to` or `on`.
        That placement remains usable after removal, but looking up its removed name
        raises `KeyError`. An empty path or traversal through an element raises `ValueError`.
        """
        return self._resolve_name(name)

    def name_of(self, placement: Placement) -> str | None:
        """The name ``placement`` was registered under, or ``None`` if unnamed."""
        return self._names.name_of(placement)

    @cached_property
    def connectors(self) -> frozenset[Connector]:
        """Unoccupied connector points in this model's frame.

        A connector disappears here when it mates with another part, including across
        nested sub-model boundaries. Covering studs can therefore change the model's
        alignment box and how subsequent parts stack on it.
        """
        in_use = self._mating.connectors
        return frozenset(
            c
            for leaf in self.flattened_placements
            for c in leaf.connectors
            if c not in in_use
        )

    @cached_property
    def bounding_box(self) -> tuple[Position, Position]:
        """The physical bounding box spanning every part's, in the model's frame.

        A sub-model holding no parts spans nothing, so a model with no parts
        returns ``(Position.ZERO, Position.ZERO)``.
        """
        boxes = [
            p.bounding_box
            for p in self.placements
            if isinstance(p.content, Element) or p.content.brick_count
        ]
        if not boxes:
            return Position.ZERO, Position.ZERO
        return vec_min([lo for lo, _ in boxes]), vec_max([hi for _, hi in boxes])

    def list_elements(self) -> Counter[Element]:
        """How many of each element -- part and color -- the model uses."""
        return Counter(leaf.content for leaf in self.flattened_placements)

    @cached_property
    def brick_count(self) -> int:
        """The total number of bricks in the model."""
        return len(self.flattened_placements)

    @cached_property
    def flattened_placements(self) -> tuple[Placement[Element], ...]:
        """Every element placement, flattened into this model's own frame.

        Flattening reaches through nested sub-models, so each leaf holds an
        :class:`Element`.
        """
        leaves: list[Placement[Element]] = []
        for placement in self.placements:
            content = placement.content
            if isinstance(content, Element):
                # Leaves keep their identity, which is how `flatten` carries
                # over the names of placements that were already leaves.
                leaves.append(cast("Placement[Element]", placement))
            else:
                leaves.extend(
                    self._compose(placement, leaf)
                    for leaf in content.flattened_placements
                )
        return tuple(leaves)

    @cached_property
    def colliding_placements(
        self,
    ) -> tuple[tuple[Placement[Element], Placement[Element]], ...]:
        """Pairs of placements whose collision volumes overlap."""
        leaves = self.flattened_placements
        return tuple(
            (leaves[i], leaves[j])
            for i, j in colliding_pairs([leaf.collision_body for leaf in leaves])
        )

    @cached_property
    def floating_placements(self) -> tuple[Placement[Element], ...]:
        """Parts without a path to the ground through connectors or contact.

        The lowest physical extent defines the ground, as in
        `translate_to_ground`. The model's poses remain unchanged, and returned
        placements are the original leaves.

        Mated connectors transmit support in both directions. Surface contacts
        transmit it from the supporting part to the part resting on it, including
        on tiles, elevated ledges, and slopes. Sliding and tipping are not checked.
        """
        leaves = self.flattened_placements
        roots = self._component_roots
        supported = {
            roots[i]
            for i, leaf in enumerate(leaves)
            if _is_grounded(leaf, self._ground)
        }
        if not supported:
            return leaves
        if supported == set(roots):
            return ()
        outgoing: dict[int, set[int]] = {}
        for i, j in self._support_edges:
            outgoing.setdefault(roots[i], set()).add(roots[j])
        pending = list(supported)
        while pending:
            for neighbor in outgoing.get(pending.pop(), ()):
                if neighbor not in supported:
                    supported.add(neighbor)
                    pending.append(neighbor)
        return tuple(leaf for i, leaf in enumerate(leaves) if roots[i] not in supported)

    @cached_property
    def connected_components(self) -> tuple[tuple[Placement[Element], ...], ...]:
        """The placements grouped by connected component.

        Each group holds the parts joined to one another through couplings, with
        the groups and the parts within them in placement order. An empty model
        has no components.
        """
        leaves = self.flattened_placements
        groups: dict[int, list[Placement[Element]]] = {}
        for i, root in enumerate(self._component_roots):
            groups.setdefault(root, []).append(leaves[i])
        # Filled in leaf order, so groups are already ordered by first member.
        return tuple(map(tuple, groups.values()))

    @cached_property
    def num_connected_components(self) -> int:
        """The number of connected components of the model."""
        return len(self.connected_components)

    def is_connected(self) -> bool:
        """Whether the model has a single connected component."""
        return self.num_connected_components == 1

    def is_valid(self) -> bool:
        """Whether the model has no collisions or floating parts."""
        return not self.colliding_placements and not self.floating_placements

    def _add_grid(
        self,
        content: Element | LegoBuild,
        *,
        ref: NameRef | Placement | None,
        offset: Position | tuple[float, float, float],
        rotation: Rotation,
        anchor: Anchor,
        target_anchor: Anchor = Anchor.FRONT_RIGHT,
        stacked: bool = False,
        name: str | None = None,
        index: int | None = None,
    ) -> Placement:
        """Record the grid placement behind :meth:`add` and :meth:`stack` --
        they differ only in ``ref`` and ``stacked``."""
        return self._place(
            grid_placement(
                content,
                reference=None if ref is None else self._reference(ref),
                offset=offset,
                rotation=rotation,
                anchor=anchor,
                target_anchor=target_anchor,
                stacked=stacked,
            ),
            name,
            index,
        )

    def _resolve_name(self, name: NameRef) -> Placement:
        """``name`` as a placement of this model, following a path if given.

        A ``str`` is tested first because a ``str`` is itself a sequence of
        ``str``, and would otherwise resolve one character at a time.
        """
        if isinstance(name, str):
            return self._names[name]
        return self._resolve_path(list(name), ())

    def _resolve_path(self, path: list[str], seen: tuple[str, ...]) -> Placement:
        """``path`` resolved from this model, composed into this model's frame.

        Each step composes onto the placement this model holds directly, so
        every key this puts in :attr:`_compose_cache` is rooted at one of this
        model's own placements -- the same shape :attr:`flattened_placements`
        produces, which is what makes a resolved path and a flattened leaf the
        same object. ``seen`` carries the names already walked, so a failure
        deeper in names the whole route.
        """
        if not path:
            raise ValueError("a name path must hold at least one name")
        head, *rest = path
        placement = self._names[head]
        if not rest:
            return placement
        content = placement.content
        if not isinstance(content, LegoBuild):
            # A well-typed path that traverses a leaf is a value problem, and
            # every sibling error in this resolution code is a ValueError.
            raise ValueError(  # noqa: TRY004
                f"{[*seen, head]} is not a sub-model, so it has no {rest[0]!r}"
            )
        return self._compose(placement, content._resolve_path(rest, (*seen, head)))

    def _reference(self, ref: NameRef | Placement) -> Placement:
        """Read a placement as geometry, or resolve a name in this model.

        Concrete placements need not belong to this model. Their poses are
        interpreted in this model's coordinate frame without conversion.
        """
        return ref if isinstance(ref, Placement) else self._resolve_name(ref)

    def _place(
        self,
        placement: Placement,
        name: str | None = None,
        index: int | None = None,
        *,
        joint: Joint | None = None,
    ) -> Placement:
        """Record ``placement`` and drop every value derived from the model's contents.

        The single door for mutation after construction: a caller cannot record
        a placement without its dependency link and its invalidation. Every
        rejection happens before anything is recorded, so a refused placement
        leaves the model exactly as it was.
        """
        self._check_placeable(placement.content)
        if index is not None:
            index = _normalized_index(index, len(self._placements), insert=True)
        if name is not None:
            self._names.register(name, placement)
        self._record(placement, index)
        if joint is not None:
            self._joints.append(joint)
        self._invalidate()
        return placement

    def _check_placeable(self, content: Element | LegoBuild) -> None:
        """Raise if placing ``content`` in this model would close a cycle.

        Raises:
            ValueError: if ``content`` is this model, or already contains it.
        """
        if not isinstance(content, Cached):
            return
        if content is self:
            raise ValueError("a model cannot contain itself")
        # A cycle closes exactly when this model is reachable from `content`
        # through the dependents ("who embeds me") graph.
        if self._has_dependent(content):
            raise ValueError(f"{content!r} already contains this model")

    def _record(self, placement: Placement, index: int | None = None) -> None:
        """Append or insert ``placement`` and link it if its content can change.

        ``index`` is already normalized. A marker equal to it stays put, so an
        empty step stays empty and an insertion at the end matches an append.
        """
        if isinstance(placement.content, Cached):
            self._depends_on(placement)
        if index is None:
            self._placements.append(placement)
        else:
            self._placements.insert(index, placement)
            self._steps = [m + 1 if m > index else m for m in self._steps]

    def _compose(
        self, outer: Placement, inner: Placement[_ContentT]
    ) -> Placement[_ContentT]:
        """``inner`` -- a placement in ``outer``'s sub-model frame -- re-expressed
        as a single placement in ``outer``'s own (host) frame.

        Memoized on ``outer`` then ``inner``, so a nested leaf's derived
        geometry survives a sibling's mutation and a placement reached by name
        is the same object as the matching flattened leaf. ``outer`` is always
        one of this model's own placements, so :meth:`_drop_composed` pops a
        whole group at once; the inner keys are weak, since the sub-model may
        drop ``inner`` without telling this model.
        """
        return self._memoized(outer, inner, lambda: inner.transformed(outer.pose))

    def _compose_joint(self, outer: Placement, inner: Joint) -> Joint:
        """Keep a nested joint's handle stable while its source record exists."""
        return self._memoized(outer, inner, lambda: prefixed(inner, (outer,)))

    def _memoized(
        self, outer: Placement, inner: Placement | Joint, make: Callable[[], _MemoT]
    ) -> _MemoT:
        """``make()``, memoized on ``outer`` then weakly on ``inner``."""
        group = self._compose_cache.setdefault(outer, WeakKeyDictionary())
        value = group.get(inner)
        if value is None:
            value = group[inner] = make()
        return value

    def _drop_cached(self) -> None:
        super()._drop_cached()
        if self._joints:
            live = set(leaf_paths(self._placements))
            self._joints[:] = [
                j
                for j in self._joints
                if j.parent.path in live and j.child.path in live
            ]

    def _drop_composed(self, placement: Placement) -> None:
        """Forget every composition rooted at ``placement``."""
        self._compose_cache.pop(placement, None)

    def _reset_compose_cache(self) -> None:
        """Start the composition memo empty."""
        self._compose_cache: dict[Placement, WeakKeyDictionary[Any, Any]] = {}

    @cached_property
    def _mating(self) -> Matings:
        """One mating scan over the flattened leaves, shared by :attr:`connectors`
        and the coupling queries. Its ``pairs`` are leaf index pairs joined by
        mated connectors, so couplings cross sub-model boundaries."""
        return mated([leaf.connectors for leaf in self.flattened_placements])

    @cached_property
    def _component_roots(self) -> list[int]:
        """Each leaf's connected-component root, by leaf index."""
        return component_roots(len(self.flattened_placements), self._mating.pairs)

    @cached_property
    def _ground(self) -> Scalar:
        """The lowest physical extent of any part.

        Not the bounding box's floor: a rotated sub-model's enclosing box can
        reach below every part.
        """
        return min(
            (leaf.bounding_box[0].z for leaf in self.flattened_placements), default=0
        )

    @cached_property
    def _support_edges(self) -> list[tuple[int, int]]:
        """Directed surface contacts between separate connector components."""
        return supporting_pairs(
            [leaf.collision_body for leaf in self.flattened_placements],
            groups=self._component_roots,
        )


def _resolve_connector(
    geometry: LegoGeometry, spec: Connector | ConnectorType | str
) -> Connector:
    """Resolve a source connector, validating concrete points by value."""
    if not isinstance(spec, Connector):
        return geometry.find_connector(spec)
    for connector in geometry.connectors:
        if same_connector(connector, spec):
            return connector
    raise ValueError(f"{spec} is not a connector of {geometry!r}")


def _is_grounded(placement: Placement, ground: float) -> bool:
    """Whether a nondegenerate part reaches the model's normalized ground."""
    lo, hi = placement.bounding_box
    return lo.z - ground < BUILD_TOLERANCE < hi.z - ground


def _normalized_index(index: int, count: int, *, insert: bool = False) -> int:
    """``index`` as a non-negative position, counting negatives from the end.

    An insertion may land just past the last placement; a lookup may not.
    Out-of-range indices raise: ``list.insert`` would clamp and hide the
    caller's bug.

    Raises:
        IndexError: if ``index`` falls outside the permitted range.
    """
    limit = count if insert else count - 1
    resolved = index + count if index < 0 else index
    if not 0 <= resolved <= limit:
        raise IndexError(
            f"index {index} is out of range for a model of {count} placements"
        )
    return resolved


def _validated_steps(steps: Iterable[int], count: int) -> tuple[int, ...]:
    """``steps`` as step-marker positions over ``count`` placements.

    Raises:
        ValueError: if a marker is negative, sits past the last placement, or
            comes before the marker ahead of it.
    """
    markers = tuple(steps)
    for marker in markers:
        if not 0 <= marker <= count:
            raise ValueError(
                f"step marker {marker} is outside a model of {count} placements"
            )
    if any(a > b for a, b in pairwise(markers)):
        raise ValueError(f"step markers must be non-decreasing, got {markers}")
    return markers


__all__ = ["LegoBuild", "NameRef"]
