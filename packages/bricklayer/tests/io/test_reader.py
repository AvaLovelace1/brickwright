"""Tests for reading LDraw (.ldr) text into a LegoBuild."""

import warnings

import pytest

from bricklayer import (
    Color,
    Element,
    LDrawImportWarning,
    LegoBuild,
    Pose,
    Position,
    Rotation,
    Vec3,
    brick,
    from_ldraw,
    plate,
    read_ldraw,
    to_ldraw,
)
from bricklayer.geometry import rotation_about
from bricklayer.modeling.placement import Placement

# A 1x1 red brick one stud in from the origin, as the writer emits it.
RED_BRICK = "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat"
BLUE_BRICK = "1 1 10 -48 10 1 0 0 0 1 0 0 0 1 3005.dat"


def only(model):
    """The model's single placement."""
    assert len(model.placements) == 1
    return model.placements[0]


@pytest.fixture
def assert_at(assert_same_pose):
    """Assert a placement sits where grid placement would have put it."""

    def _assert_at(placement, position, rotation=Rotation.DEG_0) -> None:
        expected = Placement.at(placement.content, position, rotation)
        assert_same_pose(placement.pose, expected.pose)

    return _assert_at


MPD = """0 FILE main.ldr
0 main
0 Name: main
1 16 0 0 0 1 0 0 0 1 0 0 0 1 turret.ldr
0 FILE turret.ldr
0 turret
0 Name: turret
1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat
"""


class TestElements:
    @pytest.mark.parametrize("value", ["nan", "inf", "-inf", "1e999"])
    @pytest.mark.parametrize("field", [2, 3, 4, 5, 9, 13])
    def test_nonfinite_coordinates_are_skipped(self, value, field):
        fields = RED_BRICK.split()
        fields[field] = value
        with pytest.warns(LDrawImportWarning, match="malformed line"):
            model = from_ldraw(" ".join(fields) + "\n" + BLUE_BRICK)
        assert len(model.placements) == 1
        assert model.placements[0].content.color is Color.BLUE

    def test_empty_text_is_an_empty_model(self):
        assert from_ldraw("").placements == ()

    def test_reads_a_part_and_its_color(self):
        content = only(from_ldraw(RED_BRICK)).content
        assert isinstance(content, Element)
        assert content.spec.ldraw_id == "3005"
        assert content.color is Color.RED

    def test_reads_the_position(self, assert_at):
        assert_at(only(from_ldraw(RED_BRICK)), Position(0, 0, 0))

    def test_reads_a_rotation(self, assert_at):
        # A 2x1 brick placed at the origin with a quarter turn.
        text = "1 4 10 -24 20 0 0 -1 0 1 0 1 0 0 3004.dat"
        assert_at(only(from_ldraw(text)), Position(0, 0, 0), Rotation.DEG_90)

    def test_reads_several_parts_in_order(self):
        model = from_ldraw(f"{RED_BRICK}\n{BLUE_BRICK}\n")
        assert [p.content.color for p in model.placements] == [Color.RED, Color.BLUE]

    def test_ignores_blank_lines_comments_and_geometry_primitives(self):
        lines = [
            "0 Author: somebody",
            "0 BFC CERTIFY CCW",
            "",
            RED_BRICK,
            "2 24 0 0 0 10 0 0",
            "3 16 0 0 0 1 0 0 0 1 0",
            "4 16 0 0 0 1 0 0 1 1 0 0 1 0",
            "5 24 0 0 0 1 0 0 0 1 0 0 0 1",
        ]
        assert len(from_ldraw("\n".join(lines)).placements) == 1


class TestSteps:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (f"{RED_BRICK}\n{BLUE_BRICK}", ()),
            (f"{RED_BRICK}\n0 STEP\n{BLUE_BRICK}", (1,)),
            (f"{RED_BRICK}\n0 STEP\n", (1,)),
            (f"0 STEP\n{RED_BRICK}", (0,)),
            (f"{RED_BRICK}\n0 STEP\n0 STEP\n", (1, 1)),
            (f"{RED_BRICK}\n0 ROTSTEP 0 45 0 ABS\n", (1,)),
        ],
        ids=["none", "mid-build", "trailing", "leading", "repeated", "rotstep"],
    )
    def test_step_lines_record_markers(self, text, expected):
        assert from_ldraw(text).step_markers == expected

    def test_a_repeated_marker_mid_build_records_a_mid_list_repeat(self):
        model = from_ldraw(f"{RED_BRICK}\n0 STEP\n0 STEP\n{BLUE_BRICK}\n")
        assert model.step_markers == (1, 1)
        assert [p.content.color for p in model.placements] == [Color.RED, Color.BLUE]


class TestSkips:
    def test_uncatalogued_part_warns_and_is_skipped(self):
        text = f"{RED_BRICK}\n1 4 0 0 0 1 0 0 0 1 0 0 0 1 no-such-part.dat"
        with pytest.warns(LDrawImportWarning, match="uncatalogued part 'no-such-part'"):
            model = from_ldraw(text)
        assert len(model.placements) == 1

    def test_repeated_skips_warn_once_with_a_count(self):
        bad = "1 4 0 0 0 1 0 0 0 1 0 0 0 1 no-such-part.dat"
        with pytest.warns(LDrawImportWarning, match="skipped 3 lines") as caught:
            from_ldraw("\n".join([bad] * 3))
        assert len(caught) == 1

    @pytest.mark.parametrize(
        ("text", "match"),
        [
            ("1 4 10 -24 10 -1 0 0 0 1 0 0 0 1 3005.dat", "not a rotation"),
            (
                "1 16 0 0 0 1 0 0 0 1 0 0 0 1 missing.ldr",
                "undeclared file 'missing.ldr'",
            ),
            ("1 4 10 -24 10 3005.dat", "malformed line"),
            ("1 4 x -24 10 1 0 0 0 1 0 0 0 1 3005.dat", "malformed line"),
        ],
        ids=[
            "reflection",
            "undeclared-file",
            "short-line",
            "non-numeric-field",
        ],
    )
    def test_unreadable_lines_warn_and_are_skipped(self, text, match):
        with pytest.warns(LDrawImportWarning, match=match):
            assert from_ldraw(text).placements == ()

    def test_a_clean_file_warns_about_nothing(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert len(from_ldraw(f"{RED_BRICK}\n0 STEP\n").placements) == 1


class TestPreamble:
    """Text before the first ``0 FILE`` block is not itself a block."""

    @staticmethod
    def _multipart_text():
        sub = LegoBuild()
        sub.add(brick(1, 1, color=Color.RED))
        main = LegoBuild()
        main.add(sub, name="turret")
        return to_ldraw(main)

    def test_a_blank_preamble_is_dropped_and_the_model_still_reads(self):
        text = self._multipart_text()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            model = from_ldraw("\n" + text)
        assert len(model.placements) == 1
        assert only(model).content.step_markers == ()

    def test_a_commented_preamble_is_dropped_and_the_model_still_reads(self):
        text = self._multipart_text()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            model = from_ldraw("0 Author: me\n" + text)
        assert len(model.placements) == 1

    def test_a_preamble_holding_a_placement_warns_and_is_dropped(self):
        text = f"{RED_BRICK}\n" + self._multipart_text()
        with pytest.warns(LDrawImportWarning, match="preamble"):
            model = from_ldraw(text)
        # The preamble's brick is discarded; only the MPD's own model reads.
        assert len(model.placements) == 1
        assert isinstance(model.placements[0].content, LegoBuild)


class TestByteOrderMark:
    def test_a_flat_file_reads(self):
        assert only(from_ldraw(f"\ufeff{RED_BRICK}")).content.color is Color.RED

    def test_a_multipart_file_reads(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            model = from_ldraw("\ufeff" + MPD)
        assert isinstance(only(model).content, LegoBuild)


class TestMultipart:
    def test_the_first_block_is_the_model(self):
        model = from_ldraw(MPD)
        assert len(model.placements) == 1
        assert model.placements[0].content.brick_count == 1

    def test_a_sub_file_reference_becomes_a_sub_model(self):
        sub = only(from_ldraw(MPD)).content
        assert isinstance(sub, LegoBuild)
        assert only(sub).content.spec.ldraw_id == "3005"

    def test_the_sub_file_name_names_the_placement(self):
        model = from_ldraw(MPD)
        assert model.name_of(model.placements[0]) == "turret"

    def test_a_sub_file_referenced_twice_is_one_model(self):
        text = MPD.replace(
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 turret.ldr",
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 turret.ldr\n"
            "1 16 100 0 0 1 0 0 0 1 0 0 0 1 turret.ldr",
        )
        model = from_ldraw(text)
        first, second = model.placements
        assert first.content is second.content

    def test_only_the_first_reference_takes_the_sub_file_name(self):
        # A name is unique within its host, so the second reference goes unnamed.
        text = MPD.replace(
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 turret.ldr",
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 turret.ldr\n"
            "1 16 100 0 0 1 0 0 0 1 0 0 0 1 turret.ldr",
        )
        model = from_ldraw(text)
        assert model.name_of(model.placements[0]) == "turret"
        assert model.name_of(model.placements[1]) is None

    def test_a_sub_model_keeps_its_own_step_markers(self):
        model = from_ldraw(
            MPD.replace(
                "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat",
                "1 4 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat\n0 STEP",
            )
        )
        assert model.step_markers == ()
        assert only(model).content.step_markers == (1,)

    def test_a_colored_sub_file_reference_preserves_explicit_leaf_colors(self):
        text = MPD.replace(
            "1 16 0 0 0 1 0 0 0 1 0 0 0 1 turret.ldr",
            "1 1 0 0 0 1 0 0 0 1 0 0 0 1 turret.ldr",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            model = from_ldraw(text)
        assert only(only(model).content).content.color is Color.RED

    def test_a_self_referencing_sub_file_warns_and_is_skipped(self):
        text = MPD + "1 16 0 0 0 1 0 0 0 1 0 0 0 1 turret.ldr\n"
        with pytest.warns(LDrawImportWarning, match="references itself"):
            model = from_ldraw(text)
        assert only(only(model).content).content.spec.ldraw_id == "3005"

    def test_a_blocks_first_meta_line_is_its_title(self):
        # Per the LDraw spec a file's first line is its title, whatever it says.
        text = MPD.replace("0 turret\n", "0 STEP 1\n")
        assert only(from_ldraw(text)).content.step_markers == ()

    def test_a_title_reading_like_a_file_declaration_opens_no_block(self):
        text = MPD.replace("0 turret\n", "0 FILE other\n")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            model = from_ldraw(text)
        assert only(only(model).content).content.spec.ldraw_id == "3005"

    def test_a_block_with_no_title_keeps_its_first_line(self):
        text = MPD.replace("0 turret\n0 Name: turret\n", "")
        assert only(only(from_ldraw(text)).content).content.spec.ldraw_id == "3005"

    def test_a_repeated_sub_file_declaration_warns_and_keeps_the_first(self):
        text = MPD + "0 FILE turret.ldr\n1 1 10 -24 10 1 0 0 0 1 0 0 0 1 3005.dat\n"
        with pytest.warns(LDrawImportWarning, match="repeated sub-file"):
            model = from_ldraw(text)
        assert only(only(model).content).content.color is Color.RED


class TestRoundTrip:
    """A file BrickWright wrote reads back into a model that writes the same file.

    Text is the thing asserted on: a pose that has been through a file is all
    floats, while a freshly built one holds integers and Fractions, and the
    writer rounds both to the same six decimals.
    """

    @staticmethod
    def assert_round_trips(model):
        text = to_ldraw(model)
        assert to_ldraw(from_ldraw(text)) == text

    def test_flat_model(self, model):
        model.add(brick(4, 2, color=Color.RED), Position(0, 0, 0), name="base")
        model.stack(plate(2, 2, color=Color.BLUE), "base")
        self.assert_round_trips(model)

    def test_rotated_and_elevated_parts(self, model):
        model.add(brick(2, 1, color=Color.RED), Position(0, 0, 0), Rotation.DEG_90)
        model.add(brick(2, 1, color=Color.GREEN), Position(4, 3, 2), Rotation.DEG_270)
        self.assert_round_trips(model)

    def test_a_part_whose_ldraw_pose_is_rotated(self, model, assert_at):
        # Part 60594 carries an `offset_rotation`, so the writer seats it into
        # the LDraw frame and the reader has to unseat it again.
        model.add(Element("60594", Color.WHITE), Position(0, 0, 0))
        self.assert_round_trips(model)
        assert_at(only(from_ldraw(to_ldraw(model))), Position(0, 0, 0))

    def test_nested_sub_models(self):
        inner = LegoBuild()
        inner.add(brick(2, 1, color=Color.RED))
        outer = LegoBuild()
        outer.add(inner, Position(0, 0, 0), name="left")
        outer.add(inner, Position(5, 0, 0))
        self.assert_round_trips(outer)

    def test_deeply_nested_sub_models(self):
        inner = LegoBuild()
        inner.add(brick(4, 2, color=Color.RED))
        middle = LegoBuild()
        middle.add(inner)
        outer = LegoBuild()
        outer.add(middle)
        self.assert_round_trips(outer)

    @pytest.mark.parametrize("name", ["Step 2", "FILE other", "Main", "Wing"])
    def test_sub_models_whose_names_read_like_meta_commands(self, name):
        inner = LegoBuild()
        inner.add(brick(2, 1, color=Color.RED))
        other = LegoBuild()
        other.add(brick(1, 1, color=Color.BLUE))
        outer = LegoBuild()
        outer.add(inner, Position(0, 0, 0), name=name)
        outer.add(other, Position(5, 0, 0), name=name.lower())
        self.assert_round_trips(outer)
        back = from_ldraw(to_ldraw(outer))
        assert [p.content.brick_count for p in back.placements] == [1, 1]
        assert back.placements[0].content.step_markers == ()

    def test_arbitrary_rotations(self, model):
        model.add_raw(
            brick(1, 1, color=Color.RED), Pose(rotation_about(Vec3(0, 0, 1), 28))
        )
        self.assert_round_trips(model)

    def test_step_markers(self, model):
        model.add_step()
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        model.add_step()
        model.add_step()
        model.add(brick(1, 1, color=Color.BLUE), Position(2, 0, 0))
        model.add_step()
        self.assert_round_trips(model)

    def test_a_model_with_no_markers_gains_none(self, model):
        model.add(brick(1, 1, color=Color.RED), Position(0, 0, 0))
        assert from_ldraw(to_ldraw(model)).step_markers == ()


class TestReadLdraw:
    def test_reads_from_a_file(self, tmp_path):
        path = tmp_path / "model.ldr"
        path.write_text(f"{RED_BRICK}\n")
        assert len(read_ldraw(path).placements) == 1

    def test_reads_a_file_with_non_utf8_bytes_in_a_comment(self, tmp_path):
        # LDraw is a latin-1-era format; a third-party header can carry an
        # accented author name that is not valid UTF-8 (here, byte 0xe9).
        path = tmp_path / "model.ldr"
        path.write_bytes(b"0 Author: Ren\xe9\n" + RED_BRICK.encode("ascii") + b"\n")
        assert len(read_ldraw(path).placements) == 1

    def test_reads_a_file_starting_with_a_byte_order_mark(self, tmp_path):
        path = tmp_path / "model.ldr"
        path.write_text(f"{RED_BRICK}\n", encoding="utf-8-sig")
        assert len(read_ldraw(path).placements) == 1
