"""Tests for writing a LegoBuild to LDraw (.ldr) text."""

from bricklayer import (
    Color,
    LegoBuild,
    Position,
    Rotation,
    brick,
    inverted_slope,
    plate,
    slope,
    to_ldraw,
    write_ldraw,
)


class TestToLDraw:
    def test_empty_model(self):
        assert to_ldraw(LegoBuild()) == ""

    def test_axis_mapping_to_ldraw(self, model):
        # BrickLayer (x width, y depth, z height) -> LDraw (X, -Y, Z): width
        # stays X, depth becomes Z, and height becomes negative Y. A 1x1 brick
        # at (2, 3, 1): center x=2.5 -> X=50, center y=3.5 -> Z=70. The part has
        # a top origin, so Y is its top plate-layer: z=3..5 -> top layer 6 -> -48.
        model.add(brick(1, 1, color=Color.RED), Position(2, 3, 1))
        assert to_ldraw(model) == "1 4 50 -48 70 1 0 0 0 1 0 0 0 1 3005.dat\n"

    def test_single_brick_at_origin(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0))
        # A 4x2 brick is 4 wide (X) x 2 deep (Y): footprint center is (2, 1)
        # studs -> X=40, Z=20. Top origin: a 1-brick part on the ground has its
        # top face one brick (3 plates) up -> Y=-24, the solid hanging to 0.
        assert to_ldraw(model) == "1 4 40 -24 20 1 0 0 0 1 0 0 0 1 3001.dat\n"

    def test_stacking_offsets_y_upward(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0), name="base")
        model.stack(brick(4, 2, color=Color.BLUE), "base")  # top at z=6 -> Y=-48
        line = to_ldraw(model).splitlines()[1]  # follows the base
        assert line == "1 1 40 -48 20 1 0 0 0 1 0 0 0 1 3001.dat"

    def test_rotation_writes_a_matrix(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), Rotation.DEG_90)
        # The 2x1 brick (2 wide, 1 deep) rotates to 1 wide, 2 deep: center
        # (0.5, 1) -> X=10, Z=20; top of a 1-brick part -> Y=-24.
        assert to_ldraw(model) == "1 4 10 -24 20 0 0 -1 0 1 0 1 0 0 3004.dat\n"

    def test_half_turn_writes_the_180_matrix(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0), Rotation.DEG_180)
        # A 4x2 is symmetric, so only the orientation matrix changes.
        assert to_ldraw(model) == "1 4 40 -24 20 -1 0 0 0 1 0 0 0 -1 3001.dat\n"

    def test_plate_on_brick_sits_flush(self, model):
        # The brick's top and the plate's bottom meet at Y=-24. The plate is
        # 8 LDU thick, so its top-origin coordinate is Y=-32.
        model.add(brick(2, 2, color=Color.RED), Position(0, 0, 0), name="base")
        model.stack(plate(2, 2, color=Color.BLUE), "base")
        brick_line, plate_line = to_ldraw(model).splitlines()
        assert brick_line == "1 4 20 -24 20 1 0 0 0 1 0 0 0 1 3003.dat"
        assert plate_line == "1 1 20 -32 20 1 0 0 0 1 0 0 0 1 3022.dat"

    def test_slope_is_anchored_over_its_back_row(self, model):
        # LDraw slope origins sit over the tall back row. Its center on this
        # 2x2 slope is 1.5 studs deep, giving Z=30 LDU.
        model.add(slope(2, 2, color=Color.RED), Position(0, 0, 0))
        assert to_ldraw(model) == "1 4 20 -24 30 1 0 0 0 1 0 0 0 1 3039.dat\n"

    def test_deeper_slope_back_row_offset_scales_with_depth(self, model):
        # A 4x3 slope: back row is grid y=2, center (2.5 studs) -> Z=50.
        model.add(slope(4, 3, color=Color.RED), Position(0, 0, 0))
        assert to_ldraw(model) == "1 4 40 -24 50 1 0 0 0 1 0 0 0 1 3297.dat\n"

    def test_inverted_slope_is_also_back_anchored(self, model):
        # A 2x2 inverted slope shares the back-row anchor like a 2x2 slope: Z=30.
        model.add(inverted_slope(2, 2, color=Color.RED), Position(0, 0, 0))
        assert to_ldraw(model) == "1 4 20 -24 30 1 0 0 0 1 0 0 0 1 3660b.dat\n"

    def test_a_flat_model_is_not_wrapped_in_a_subfile(self, model):
        # No sub-models -> plain type-1 lines, no MPD `0 FILE` headers.
        model.add(brick(4, 2, color=Color.RED))
        assert "0 FILE" not in to_ldraw(model)


class TestSteps:
    """`0 STEP` is written where the model records a build-step marker, and
    nowhere else."""

    def test_no_markers_writes_no_step_lines(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0), name="a")
        model.stack(brick(1, 1, color=Color.BLUE), "a")
        assert to_ldraw(model).splitlines() == [
            "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
            "1 1 10 -48 10 1 0 0 0 1 0 0 0 1 3005.dat",
        ]

    def test_a_marker_writes_a_step_line_at_its_position(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0), name="a")
        model.add_step()
        model.stack(brick(1, 1, color=Color.BLUE), "a")
        assert to_ldraw(model).splitlines() == [
            "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
            "0 STEP",
            "1 1 10 -48 10 1 0 0 0 1 0 0 0 1 3005.dat",
        ]

    def test_a_trailing_marker_writes_a_final_step_line(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add_step()
        assert to_ldraw(model).splitlines() == [
            "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
            "0 STEP",
        ]

    def test_repeated_markers_write_consecutive_step_lines(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add_step()
        model.add_step()
        assert to_ldraw(model).splitlines() == [
            "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
            "0 STEP",
            "0 STEP",
        ]

    def test_a_leading_marker_writes_a_step_line_first(self, model):
        model.add_step()
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        assert to_ldraw(model).splitlines() == [
            "0 STEP",
            "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
        ]

    def test_repeated_markers_mid_build_write_consecutive_step_lines_between_parts(
        self, model
    ):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0), name="a")
        model.add_step()
        model.add_step()
        model.stack(brick(1, 1, color=Color.BLUE), "a")
        assert to_ldraw(model).splitlines() == [
            "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
            "0 STEP",
            "0 STEP",
            "1 1 10 -48 10 1 0 0 0 1 0 0 0 1 3005.dat",
        ]

    def test_a_submodel_keeps_its_own_markers(self):
        # Markers are per-model, so a sub-file's steps are its own.
        sub = LegoBuild()
        sub.add(brick(1, 1, color=Color.RED))
        sub.add_step()
        outer = LegoBuild()
        outer.add(sub, name="turret")
        assert to_ldraw(outer).splitlines() == [
            "0 FILE main.ldr",
            "0 main",
            "0 Name: main",
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 turret.ldr",
            "0 FILE turret.ldr",
            "0 turret",
            "0 Name: turret",
            "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
            "0 STEP",
        ]


class TestSubModelStructure:
    """A nested model becomes an MPD: one `0 FILE` block per distinct sub-model,
    referenced by a type-1 line that points at the sub-file."""

    def test_reference_transform_carries_rotation_and_position(self):
        # A sub-model holds its part in its own frame; the reference line carries
        # the placement transform. Placing the bar (2 wide, 1 deep) at (5, 0)
        # rotated a quarter turn must reproduce the part's world position.
        bar = LegoBuild()
        bar.add(brick(2, 1, color=Color.RED))
        outer = LegoBuild()
        outer.add(bar, Position(5, 0, 0), Rotation.DEG_90)
        assert to_ldraw(outer).splitlines() == [
            "0 FILE main.ldr",
            "0 main",
            "0 Name: main",
            "1 16 120 0 0 0 0 -1 0 1 0 1 0 0 submodel.ldr",
            "0 FILE submodel.ldr",
            "0 submodel",
            "0 Name: submodel",
            "1 4 20 -24 10 1 0 0 0 1 0 0 0 1 3004.dat",
        ]

    def test_reference_transform_at_270_with_elevation(self):
        # A 270-degree turn, off the origin, one brick up: exercises the
        # re-anchor offset, both horizontal axes, and the vertical sign.
        bar = LegoBuild()
        bar.add(brick(2, 1, color=Color.RED))  # 2 wide, 1 deep
        outer = LegoBuild()
        outer.add(bar, Position(3, 4, 1), Rotation.DEG_270)
        assert to_ldraw(outer).splitlines() == [
            "0 FILE main.ldr",
            "0 main",
            "0 Name: main",
            "1 16 60 -24 120 0 0 1 0 1 0 -1 0 0 submodel.ldr",
            "0 FILE submodel.ldr",
            "0 submodel",
            "0 Name: submodel",
            "1 4 20 -24 10 1 0 0 0 1 0 0 0 1 3004.dat",
        ]

    def test_same_submodel_placed_twice_is_defined_once(self):
        # Held by reference: one definition, two references at different spots.
        bar = LegoBuild()
        bar.add(brick(2, 1, color=Color.RED))
        outer = LegoBuild()
        outer.add(bar, Position(0, 0, 0))
        outer.add(bar, Position(5, 0, 0))
        text = to_ldraw(outer)
        assert text.count("0 FILE submodel.ldr") == 1  # defined once
        assert text.count("submodel.ldr") == 3  # 1 definition + 2 references

    def test_deep_nesting_writes_a_block_per_level(self):
        inner = LegoBuild()
        inner.add(brick(4, 2, color=Color.RED))
        middle = LegoBuild()
        middle.add(inner)
        outer = LegoBuild()
        outer.add(middle)
        assert to_ldraw(outer).splitlines() == [
            "0 FILE main.ldr",
            "0 main",
            "0 Name: main",
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 submodel.ldr",
            "0 FILE submodel.ldr",
            "0 submodel",
            "0 Name: submodel",
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 submodel_2.ldr",
            "0 FILE submodel_2.ldr",
            "0 submodel_2",
            "0 Name: submodel_2",
            "1 4 40 -24 20 1 0 0 0 1 0 0 0 1 3001.dat",
        ]

    def test_named_submodel_uses_name_as_filename(self):
        sub = LegoBuild()
        sub.add(brick(1, 1, color=Color.RED))
        outer = LegoBuild()
        outer.add(sub, name="my_submodel")
        assert to_ldraw(outer).splitlines() == [
            "0 FILE main.ldr",
            "0 main",
            "0 Name: main",
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 my_submodel.ldr",
            "0 FILE my_submodel.ldr",
            "0 my_submodel",
            "0 Name: my_submodel",
            "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
        ]

    def test_distinct_submodels_sharing_a_name_get_unique_filenames(self):
        # A name is unique only within its host model, so two *distinct* sub-models
        # placed in different hosts can carry the same name. They must not collapse
        # onto one sub-file: each needs its own `0 FILE` block, so the second's name
        # is disambiguated.
        inner_a = LegoBuild()
        inner_a.add(brick(1, 1, color=Color.RED))
        host_a = LegoBuild()
        host_a.add(inner_a, name="wall")
        inner_b = LegoBuild()
        inner_b.add(brick(1, 1, color=Color.BLUE))
        host_b = LegoBuild()
        host_b.add(inner_b, name="wall")
        outer = LegoBuild()
        outer.add(host_a, Position(0, 0, 0))
        outer.add(host_b, Position(5, 0, 0))

        lines = to_ldraw(outer).splitlines()
        file_names = [ln[len("0 FILE ") :] for ln in lines if ln.startswith("0 FILE ")]
        # main + the two hosts + the two distinct "wall" sub-files, all unique.
        assert sorted(file_names) == [
            "main.ldr",
            "submodel.ldr",
            "submodel_2.ldr",
            "wall.ldr",
            "wall_2.ldr",
        ]
        # Each "wall" sub-file is referenced exactly once (no shared reference).
        assert lines.count("1 16 0 0 0 1 0 0 0 1 0 0 0 1 wall.ldr") == 1
        assert lines.count("1 16 0 0 0 1 0 0 0 1 0 0 0 1 wall_2.ldr") == 1

    def test_a_submodel_named_like_main_gets_its_own_file(self):
        # LDraw file names are case-insensitive, so "Main.ldr" is "main.ldr".
        sub = LegoBuild()
        sub.add(brick(1, 1, color=Color.RED))
        outer = LegoBuild()
        outer.add(sub, name="Main")
        assert "0 FILE Main_2.ldr" in to_ldraw(outer).splitlines()

    def test_submodels_differing_only_in_case_get_distinct_files(self):
        wing = LegoBuild()
        wing.add(brick(1, 1, color=Color.RED))
        other = LegoBuild()
        other.add(brick(1, 1, color=Color.BLUE))
        outer = LegoBuild()
        outer.add(wing, Position(0, 0, 0), name="Wing")
        outer.add(other, Position(5, 0, 0), name="wing")
        lines = to_ldraw(outer).splitlines()
        assert "0 FILE Wing.ldr" in lines
        assert "0 FILE wing_2.ldr" in lines

    def test_blocks_carry_a_name_matching_the_file(self):
        # After each `0 FILE` line, `0 <name>` and `0 Name: <name>` (extension
        # stripped) let Studio show the file's name. The main block is named too.
        sub = LegoBuild()
        sub.add(brick(1, 1, color=Color.RED))
        outer = LegoBuild()
        outer.add(sub, name="turret")
        lines = to_ldraw(outer).splitlines()
        assert lines[:3] == ["0 FILE main.ldr", "0 main", "0 Name: main"]
        i = lines.index("0 FILE turret.ldr")
        assert lines[i : i + 3] == [
            "0 FILE turret.ldr",
            "0 turret",
            "0 Name: turret",
        ]

    def test_named_and_unnamed_submodels_coexist(self):
        # A named placement names its sub-file; unnamed ones keep sequential
        # `submodel{n}` numbering, counted independently of the named ones.
        sub_a = LegoBuild()
        sub_a.add(brick(1, 1, color=Color.RED))
        sub_b = LegoBuild()
        sub_b.add(brick(1, 1, color=Color.BLUE))
        outer = LegoBuild()
        outer.add(sub_a, Position(0, 0, 0), name="alpha")
        outer.add(sub_b, Position(2, 0, 0))  # unnamed
        assert to_ldraw(outer).splitlines() == [
            "0 FILE main.ldr",
            "0 main",
            "0 Name: main",
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 alpha.ldr",
            "1 16 40 0 0 1 0 0 0 1 0 0 0 1 submodel.ldr",
            "0 FILE alpha.ldr",
            "0 alpha",
            "0 Name: alpha",
            "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
            "0 FILE submodel.ldr",
            "0 submodel",
            "0 Name: submodel",
            "1 1 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
        ]


def test_writer_uses_the_spec_ldraw_id() -> None:
    model = LegoBuild()
    model.add(brick(1, 1))
    assert "3005.dat" in to_ldraw(model)


class TestWriteLdraw:
    def test_writes_to_file(self, model, tmp_path):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0))
        path = tmp_path / "model.ldr"
        write_ldraw(model, path)
        assert path.read_text(encoding="utf-8") == to_ldraw(model)

    def test_nested_rotations_and_offsets(self, file_regression):
        # An "arrow" sub-assembly built from asymmetric bricks: a 4x1 bar with a 2x1
        # stub off its side, so any rotation is obvious in the output (a 4-long bar
        # that turns 90 degrees becomes 4 deep instead of 4 wide).
        arrow = LegoBuild()
        arrow.add(brick(4, 1, color=Color.RED), Position(0, 0, 0))
        arrow.add(brick(2, 1, color=Color.BLUE), Position(0, 1, 0))

        # Middle layer: two arrows, one turned a quarter turn and shifted, so the
        # sub-model is itself asymmetric before the outer layer rotates it again.
        wing = LegoBuild()
        wing.add(arrow, Position(0, 0, 0), Rotation.DEG_0)
        wing.add(arrow, Position(6, 2, 0), Rotation.DEG_90)

        # Outer layer: the whole wing placed twice, at different rotations, offsets,
        # and elevations -- three levels of nesting, each with its own transform.
        model = LegoBuild()
        model.add(wing, Position(0, 0, 0), Rotation.DEG_180)
        model.add(wing, Position(2, 8, 2), Rotation.DEG_270)

        file_regression.check(to_ldraw(model), extension=".ldr")
