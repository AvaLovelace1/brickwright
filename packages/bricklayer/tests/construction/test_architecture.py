"""Tests for the architecture components."""

import math

import pytest

from bricklayer import (
    Box,
    Color,
    Direction,
    DoorVariant,
    Element,
    FrameVariant,
    HeightLike,
    LegoBuild,
    Mat3,
    Pane,
    PaneVariant,
    PartSpec,
    Placement,
    Pose,
    Position,
    Vec3,
    door,
    to_ldraw,
    window,
)
from bricklayer.construction import architecture
from bricklayer.construction.architecture import (
    _ANGLED_CORNER_FRAME,
    _DOORS,
    _FRAMES,
    _LONG_AIRPLANE_FRAME,
    _PANES,
    _ROUND_CORNER_FRAME,
    _SEATING,
    _SEATING_FAMILIES,
    compatible_inserts,
    frame_and_insert_compatible,
    insert_dimensions,
    seating,
)
from bricklayer.construction.basic import _BRICKS
from bricklayer.geometry.linalg import EPSILON, all_close, rotation_about

_INSERT_OPTIONS = (_PANES, _DOORS)


@pytest.fixture
def patch_factory_parts(monkeypatch):
    def patch(rows):
        for table in (
            _BRICKS,
            _FRAMES,
            _PANES,
            _DOORS,
        ):
            monkeypatch.delattr(table, "specs")  # drop the cached specs
            monkeypatch.setattr(
                table,
                "parts",
                {
                    pid: variant
                    for pid, (option, variant) in rows.items()
                    if option is table
                },
            )
        return tuple(PartSpec(pid) for pid in rows)

    return patch


@pytest.fixture
def insert_of(element_of):
    def _insert_of(model):
        return element_of(model, "insert")

    return _insert_of


@pytest.fixture
def frame_of(element_of):
    def _frame_of(model):
        return element_of(model, "frame")

    return _frame_of


def _insert_placements_of(
    model: LegoBuild, n_inserts: int = 1
) -> tuple[Placement, ...]:
    result = []
    names = (
        ("insert",)
        if n_inserts == 1
        else tuple(f"insert_{i + 1}" for i in range(n_inserts))
    )
    for name in names:
        result.append(model.named(name))
    return tuple(result)


def _inserts_of(model: LegoBuild, n_inserts: int = 1) -> tuple[Element, ...]:
    result = []
    for placement in _insert_placements_of(model, n_inserts):
        assert isinstance(placement.content, Element)
        result.append(placement.content)
    return tuple(result)


def _insert_combos() -> tuple[
    tuple[int, int, HeightLike, PaneVariant | DoorVariant, FrameVariant | None], ...
]:
    """Every ``(width, depth, height, variant, frame_variant)`` a window or door can build."""
    combos = []
    for frame_spec in _FRAMES.specs:
        for options in _INSERT_OPTIONS:
            for insert_spec in compatible_inserts(frame_spec, options).values():
                assert isinstance(
                    options.variant(insert_spec), (PaneVariant, DoorVariant)
                )
                assert isinstance(
                    _FRAMES.variant(frame_spec), (FrameVariant, type(None))
                )
                assert isinstance(frame_spec.shape, Box)
                w, d, h = (
                    frame_spec.shape.width,
                    frame_spec.shape.depth,
                    frame_spec.shape.height,
                )
                insert_variant = options.variant(insert_spec)
                frame_variant = _FRAMES.variant(frame_spec)
                assert isinstance(insert_variant, (PaneVariant, DoorVariant))
                assert frame_variant is None or isinstance(frame_variant, FrameVariant)
                combos.append((w, d, h, insert_variant, frame_variant))
    return tuple(combos)


_INSERT_COMBOS = _insert_combos()


def _insert_combo_params() -> list:
    """Every buildable combo as a parametrization, one id per combo."""
    return [
        pytest.param(
            combo, id=f"{combo[0]}x{combo[1]}x{combo[2]}-{combo[3]}-{combo[4]}"
        )
        for combo in _INSERT_COMBOS
    ]


_DOOR_COMBOS = tuple(
    combo for combo in _INSERT_COMBOS if isinstance(combo[3], DoorVariant)
)


# An axis is either aligned with the build grid or genuinely tilted; the frames
# measure 0.0, 0.75, and 1.0, so nothing sits near this margin.
_AXIS_ALIGNED_MARGIN = 0.01


def _seats_its_insert_tilted(frame_elem: Element) -> bool:
    """Whether this frame's own geometry says it cannot hold an insert upright.

    Read off the part's measured seating connectors: an axis that points neither
    along z nor within the horizontal plane leans out of the vertical, and an
    insert mated to it leans with it. Derived from the part rather than from
    ``_SEATING``, so it is an independent statement of what the frame does.
    """
    return any(
        _AXIS_ALIGNED_MARGIN < abs(float(c.axis[2])) < 1 - _AXIS_ALIGNED_MARGIN
        for c in frame_elem.connectors
        if c.type.family in _SEATING_FAMILIES
    )


def _angle_from_upright(rotation: Mat3) -> float:
    """Return the angle in degrees between the given rotation and upright."""
    return math.degrees(math.acos((rotation @ Vec3(0, 0, 1)).z))


def _assert_centers_offset(
    a: Placement, b: Placement, offset: Position = Position.ZERO, tol: float = 0.2
) -> None:
    """Assert that the center of ``b`` is offset from the center of ``a`` by ``offset``
    within ``tol``, in the x and z axes only."""
    a_pos = a.pose.apply(a.content.center) + offset
    b_pos = b.pose.apply(b.content.center)
    assert abs(a_pos.x - b_pos.x) < tol
    assert abs(a_pos.z - b_pos.z) < tol


# A frame and an insert of matching dimensions, for the helpers that read a
# part's attributes only. They come from the catalog rather than being written
# out: a spec is an LDraw id and nothing else, so only a real part has attributes.
_FRAME_4X1X6 = _FRAMES.find(Box(4, 1, 6))
_PANE_4X6 = _PANES.find(Pane(4, 6), PaneVariant.SOLID)


@pytest.fixture(autouse=True)
def reset_cache():
    compatible_inserts.cache_clear()
    yield
    compatible_inserts.cache_clear()


class TestSeating:
    def test_every_insert_seats_upright_unless_its_frame_leans(self, frame_of):
        """An insert stands upright exactly when its frame's seating geometry does.

        The expectation comes from the frame part's own connectors, not from
        ``_SEATING``: reading the table back would pass whatever it said.
        The tilt *angle* is pinned behaviourally elsewhere -- a wrong one seats
        the insert into the frame instead of in it, which
        ``test_selected_pane_and_door_combo_builds`` catches as an
        invalid model.
        """
        assert _INSERT_COMBOS
        seen_tilted = seen_upright = False
        for w, d, h, variant, frame_variant in _INSERT_COMBOS:
            frame_spec = _FRAMES.find(Box(w, d, h), frame_variant)
            if isinstance(variant, DoorVariant):
                model = door(w, d, h, door_variant=variant, frame_variant=frame_variant)
            else:
                model = window(
                    w, d, h, pane_variant=variant, frame_variant=frame_variant
                )
            frame_placed = model.named("frame")
            n_inserts = seating(frame_spec).count
            insert_placements = _insert_placements_of(model, n_inserts)

            leans = _seats_its_insert_tilted(frame_of(model))
            seen_tilted |= leans
            seen_upright |= not leans
            for insert_placed in insert_placements:
                actual_angle = _angle_from_upright(insert_placed.pose.rotation)
                assert (actual_angle > EPSILON) == leans, (
                    f"{frame_spec} seats its insert at {actual_angle} degrees "
                    f"from upright; its geometry says leans={leans}"
                )
                if seating(frame_spec).count == 1 and seating(frame_spec).turn == 0:
                    # Standard frames should center the pane in the frame
                    _assert_centers_offset(frame_placed, insert_placed, tol=0.2)
        # Both sides of the claim are exercised, so a filter stuck either way fails.
        assert seen_tilted and seen_upright

    def test_insert_in_angled_corner_is_turned_to_face_the_corner(self):
        frame_variant = _FRAMES.variant(_ANGLED_CORNER_FRAME)
        assert isinstance(frame_variant, FrameVariant)
        angled_corner_inserts = [
            (w, d, h, v)
            for w, d, h, v, fv in _INSERT_COMBOS
            if fv is FrameVariant.ANGLED_CORNER
        ]
        assert angled_corner_inserts

        expected = rotation_about(
            Direction.UP.value, seating(_ANGLED_CORNER_FRAME).turn
        )
        for w, d, h, variant in angled_corner_inserts:
            if isinstance(variant, DoorVariant):
                model = door(w, d, h, door_variant=variant, frame_variant=frame_variant)
            else:
                model = window(
                    w, d, h, pane_variant=variant, frame_variant=frame_variant
                )
            pose = _insert_placements_of(model)[0].pose
            assert all_close(pose.rotation, expected, tol=1e-4)


class TestInsertDimensions:
    def test_insert_dimensions_match_frame_dimensions(self):
        assert insert_dimensions(_FRAME_4X1X6) == (4, 6)

    def test_special_cases(self):
        """A special-case frame's insert is sized differently from the frame
        itself -- the entire reason ``insert_dimensions`` cannot just read the
        frame's own shape, and why the table exists at all. And whatever size
        it reports must be a size some real Pane/Door part actually is: an
        oracle independent of ``compatible_inserts``, which legitimately
        returns nothing for both of today's special cases (their only
        same-size candidates are excluded by ``_COLLIDING_COMBOS`` for
        reasons unrelated to size), so it cannot by itself prove the table's
        numbers are real catalogue sizes rather than junk."""
        special_frames = [f for f, s in _SEATING.items() if s.insert is not None]
        assert special_frames
        real_insert_sizes = {
            (spec.shape.width, spec.shape.height)
            for spec in (
                *_PANES.specs,
                *_DOORS.specs,
            )
            if isinstance(spec.shape, Pane)
        }
        for frame_spec in special_frames:
            assert isinstance(frame_spec.shape, Box)
            insert_width, insert_height = insert_dimensions(frame_spec)
            assert (insert_width, insert_height) != (
                frame_spec.shape.width,
                frame_spec.shape.height,
            ), frame_spec
            assert (insert_width, insert_height) in real_insert_sizes, frame_spec

            # Any insert compatible_inserts *does* offer must agree with the
            # table, not the frame's own dimensions -- that agreement is what
            # makes a filled frame fit.
            for options in _INSERT_OPTIONS:
                for insert_spec in compatible_inserts(frame_spec, options).values():
                    assert isinstance(insert_spec.shape, Pane)
                    assert (insert_spec.shape.width, insert_spec.shape.height) == (
                        insert_width,
                        insert_height,
                    ), (frame_spec, insert_spec)

    def test_rejects_non_frame(self):
        with pytest.raises(ValueError, match="must be a frame"):
            insert_dimensions(_PANE_4X6)


class TestFrameAndInsertCompatible:
    @pytest.mark.parametrize(
        "insert_options", (_PANES, _DOORS), ids=lambda c: c.display_name
    )
    def test_standard_frame_compatible_with_insert_of_same_dimensions(
        self, patch_factory_parts, insert_options
    ):
        # Real ids, borrowed for the sizes their LDraw names give: a 4x1x6
        # frame, a 4x6 insert that fits it, and a 6x6 one that does not.
        frame, fits, too_wide = patch_factory_parts(
            {
                "60596": (_FRAMES, None),
                "57895": (insert_options, None),
                "42509": (insert_options, None),
            }
        )
        assert frame_and_insert_compatible(frame, fits)
        assert not frame_and_insert_compatible(frame, too_wide)

    def test_muntined_frame_incompatible_with_door(self, patch_factory_parts):
        frame, door_leaf = patch_factory_parts(
            {
                "57894": (_FRAMES, FrameVariant.THREE_PANES),
                "60616a": (_DOORS, None),
            }
        )
        assert not frame_and_insert_compatible(frame, door_leaf)

    def test_rejects_non_frame(self):
        with pytest.raises(ValueError, match="must be a frame"):
            frame_and_insert_compatible(
                _PANE_4X6,
                _PANE_4X6,
            )

    def test_rejects_non_insert(self):
        with pytest.raises(ValueError, match="must be a pane or door"):
            frame_and_insert_compatible(
                _FRAME_4X1X6,
                _FRAME_4X1X6,
            )


class TestCompatibleInserts:
    def test_finds_all_compatible_inserts_for_frame(
        self, patch_factory_parts, monkeypatch
    ):
        # This is about matching an insert to a frame's dimensions, so the real
        # colliding-combo list is out of scope; test_excludes_special_incompatible_pairs
        # covers that.
        monkeypatch.setattr(architecture, "_COLLIDING_COMBOS", frozenset())
        architecture.compatible_inserts.cache_clear()
        frame_spec, solid_pane, grille_pane, solid_door, _wide, _brick = (
            patch_factory_parts(
                {
                    "60596": (_FRAMES, None),
                    "57895": (_PANES, PaneVariant.SOLID),
                    "92589": (_PANES, PaneVariant.GRILLE),
                    "60616a": (_DOORS, DoorVariant.SOLID),
                    "42509": (_PANES, PaneVariant.SOLID),
                    "3001": (_BRICKS, None),
                }
            )
        )
        assert compatible_inserts(frame_spec, _PANES) == {
            PaneVariant.SOLID: solid_pane,
            PaneVariant.GRILLE: grille_pane,
        }
        assert compatible_inserts(frame_spec, _DOORS) == {
            DoorVariant.SOLID: solid_door,
        }

    def test_excludes_special_incompatible_pairs(self, patch_factory_parts):
        frame_spec, _door = patch_factory_parts(
            {
                "57894": (_FRAMES, FrameVariant.THREE_PANES),
                "60616a": (_DOORS, DoorVariant.SOLID),
            }
        )
        assert compatible_inserts(frame_spec, _DOORS) == {}


class TestFrame:
    def test_selected_frame_builds(self, assert_cuboid_geometry):
        for spec in _FRAMES.specs:
            assert isinstance(spec.shape, Box)
            w, d, h = spec.shape.dimensions
            assert_cuboid_geometry(spec, w, d, h, tol=0.02)


class TestWindow:
    def test_pane_and_frame_colors_are_independent(self, insert_of, frame_of):
        color, frame_color = Color.RED, Color.BLUE
        model = window(4, 1, 6, pane_color=color, frame_color=frame_color)
        assert insert_of(model).color is color
        assert frame_of(model).color is frame_color

    def test_pane_and_frame_variants_are_independent(self, insert_of, frame_of):
        variant, frame_variant = PaneVariant.LATTICE, FrameVariant.ARCHED
        filled = window(2, 1, 2, pane_variant=variant, frame_variant=frame_variant)
        assert (_PANES if isinstance(variant, PaneVariant) else _DOORS).variant(
            insert_of(filled).spec
        ) is variant
        assert _FRAMES.variant(frame_of(filled).spec) is frame_variant

    def test_spun_window_stays_valid_and_connected(self):
        filled = window(4, 1, 3)
        spin = rotation_about(Direction.UP.value, 37)
        model = LegoBuild([Placement(filled, Pose(spin))])
        assert model.is_valid()
        assert model.is_connected()

    def test_unavailable_pane_lists_the_options(self, patch_factory_parts):
        patch_factory_parts(
            {
                "60599": (_FRAMES, None),
                "57895": (_PANES, PaneVariant.SOLID),
                "92589": (_PANES, PaneVariant.GRILLE),
                "79730": (_DOORS, DoorVariant.PET),
            }
        )
        with pytest.raises(ValueError) as exc:
            window(4, 2, 6, pane_variant=PaneVariant.LATTICE)
        message = str(exc.value)
        assert "not an available" in message
        options = message.split("available panes: ")[1].split(", ")
        # The panes this frame does seat, and not the door that also fits it.
        assert set(options) == {"Solid", "Grille"}
        assert "Pet" not in options

    def test_a_door_variant_is_rejected_as_a_pane(self):
        with pytest.raises(TypeError, match="'Solid' is not a pane variant"):
            window(4, 1, 6, pane_variant=DoorVariant.SOLID)  # ty: ignore[invalid-argument-type]


class TestDoor:
    def test_door_and_frame_colors_are_independent(self, insert_of, frame_of):
        color, frame_color = Color.RED, Color.BLUE
        model = door(4, 1, 6, door_color=color, frame_color=frame_color)
        assert insert_of(model).color is color
        assert frame_of(model).color is frame_color

    def test_door_and_frame_variants_are_independent(self, insert_of, frame_of):
        variant, frame_variant = DoorVariant.PET, None
        filled = door(4, 1, 6, door_variant=variant, frame_variant=frame_variant)
        assert (_PANES if isinstance(variant, PaneVariant) else _DOORS).variant(
            insert_of(filled).spec
        ) is variant
        assert _FRAMES.variant(frame_of(filled).spec) is frame_variant

    def test_a_pane_variant_is_rejected_as_a_door(self):
        with pytest.raises(TypeError, match="'Grille' is not a door variant"):
            door(4, 1, 6, door_variant=PaneVariant.GRILLE)  # ty: ignore[invalid-argument-type]

    def test_door_in_muntined_frame_rejected(self):
        with pytest.raises(ValueError, match="cannot open through"):
            door(4, 1, 6, frame_variant=FrameVariant.THREE_PANES)

    def test_spun_door_stays_valid_and_connected(self):
        filled = door(4, 1, 6)
        spin = rotation_about(Direction.UP.value, 37)
        model = LegoBuild([Placement(filled, Pose(spin))])
        assert model.is_valid()
        assert model.is_connected()

    @pytest.mark.parametrize("angle", [0, 30, 60, 90])
    def test_posed_door_is_upright(self, angle):
        assert _DOOR_COMBOS
        for w, d, h, variant, frame_variant in _DOOR_COMBOS:
            assert isinstance(variant, DoorVariant)
            model = door(
                w,
                d,
                h,
                door_variant=variant,
                frame_variant=frame_variant,
                open_angle=angle,
            )
            pose = _insert_placements_of(model)[0].pose
            assert abs(_angle_from_upright(pose.rotation)) < EPSILON

    def test_door_opens_to_the_front(self):
        assert _DOOR_COMBOS
        for w, d, h, variant, frame_variant in _DOOR_COMBOS:
            assert isinstance(variant, DoorVariant)
            shut = door(
                w, d, h, door_variant=variant, frame_variant=frame_variant, open_angle=0
            )
            ajar = door(
                w,
                d,
                h,
                door_variant=variant,
                frame_variant=frame_variant,
                open_angle=90,
            )
            shut_min_y, shut_max_y = shut.bounding_box[0].y, shut.bounding_box[1].y
            ajar_min_y, ajar_max_y = ajar.bounding_box[0].y, ajar.bounding_box[1].y
            assert ajar_max_y == shut_max_y
            assert ajar_min_y < shut_min_y

    @pytest.mark.parametrize("bad", [-1, 91, 180])
    def test_door_open_angle_out_of_range_rejected(self, bad):
        with pytest.raises(ValueError, match="between 0 and 90"):
            door(4, 1, 6, open_angle=bad)

    def test_door_open_states_ldraw(self, model, file_regression):
        for column, open_angle in enumerate([0, 30, 60, 90]):
            model.add(
                door(4, 1, 6, open_angle=open_angle),
                Position(column * 6, 0, 0),
                name=f"door_{open_angle}",
            )
        file_regression.check(
            to_ldraw(model),
            extension=".ldr",
            basename="door_open_states",
        )


class TestFilledFrame:
    @pytest.mark.parametrize("combo", _insert_combo_params())
    def test_selected_pane_and_door_combo_builds(
        self, combo, assert_cuboid_geometry, frame_of
    ):
        w, d, h, variant, frame_variant = combo
        frame_spec = _FRAMES.find(Box(w, d, h), frame_variant)
        insert_options = _DOORS if isinstance(variant, DoorVariant) else _PANES
        if isinstance(variant, DoorVariant):
            model = door(w, d, h, door_variant=variant, frame_variant=frame_variant)
        else:
            model = window(w, d, h, pane_variant=variant, frame_variant=frame_variant)
        n_inserts = seating(frame_spec).count
        insert_elems = _inserts_of(model, n_inserts)
        frame_elem = frame_of(model)

        assert model.is_valid()
        assert model.is_connected()
        # A few doors have knobs that extend beyond the frame, so model bounding box tol is high
        assert_cuboid_geometry(model, w, d, h, tol=0.75)
        assert_cuboid_geometry(frame_elem, w, d, h, tol=0.02)
        assert frame_elem.ldraw_id in _FRAMES.parts, frame_elem
        for insert_elem in insert_elems:
            assert insert_elem.ldraw_id in insert_options.parts, insert_elem


class TestMultipleInserts:
    """Two frames -- the round corner and the long airplane -- seat *two*
    inserts rather than one.

    Both currently sit in ``_COLLIDING_COMBOS``, so no ordinary ``window()``
    call reaches that path and nothing else in the suite notices if the frames
    stop being treated as two-seat: they would quietly get one insert instead
    of two.

    **Why they collide is a data bug, not a builder bug.** Each frame exposes
    only *one* ``frame_slot`` connector -- 73878 and 61345 both have exactly
    one, hand-authored in ``part_connectivity_overrides.json``; BrickNet's
    generated ``part_connectivity.json`` gives them none at all -- while
    ``_SEATING`` says they seat two. ``find_connectors(toward=...)``
    only *orders* candidates, it does not filter, so with a single candidate
    both inserts resolve to the same seat pair and land at the same pose. The
    frames are fine; the connector data is incomplete.

    So this test pins only the builder's half of the contract -- one placement
    per listed seat -- and deliberately does **not** assert ``is_valid()``,
    because the parts genuinely do overlap given today's data.

    When the missing ``frame_slot`` connectors are added: drop these frames
    from ``_COLLIDING_COMBOS``, delete the ``every_insert_fits`` fixture below,
    and **restore the ``is_valid()`` assertion** -- at that point two inserts
    should seat at two distinct poses and the model should be valid.
    """

    @pytest.fixture(autouse=True)
    def every_insert_fits(self, monkeypatch):
        """Clear the colliding-combo list, which is what keeps these two frames
        from accepting any insert at all.

        Delete this fixture once the missing ``frame_slot`` connectors land --
        see the class docstring.
        """
        monkeypatch.setattr(architecture, "_COLLIDING_COMBOS", frozenset())
        compatible_inserts.cache_clear()

    @pytest.mark.parametrize(
        "frame_spec",
        [_ROUND_CORNER_FRAME, _LONG_AIRPLANE_FRAME],
        ids=["round_corner", "long_airplane"],
    )
    def test_a_two_seat_frame_is_filled_with_two_panes(self, frame_spec):
        assert isinstance(frame_spec.shape, Box)
        width, depth, height = frame_spec.shape.dimensions
        variant = _FRAMES.variant(frame_spec)
        assert variant is None or isinstance(variant, FrameVariant)
        model = window(width, depth, height, frame_variant=variant)
        panes = [
            placement.content
            for placement in model.flattened_placements
            if isinstance(placement.content, Element)
            and placement.content.ldraw_id in _PANES.parts
        ]
        assert len(panes) == 2
        assert panes[0].spec == panes[1].spec  # one frame seats copies of one pane
