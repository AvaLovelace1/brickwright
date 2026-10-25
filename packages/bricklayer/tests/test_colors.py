"""Tests for the fixed LEGO color palette."""

import pytest

from bricklayer import Color, Finish
from bricklayer.colors import hex2rgb, linear_rgb


class TestHex2Rgb:
    def test_hex2rgb_parses_each_byte_in_order(self):
        assert hex2rgb("C91A09") == (201, 26, 9)
        assert hex2rgb("FF8000") == (255, 128, 0)
        assert hex2rgb("123456") == (18, 52, 86)

    def test_hex2rgb_rejects_malformed_input(self):
        with pytest.raises(ValueError, match="invalid hex"):
            hex2rgb("12345")

    def test_rgb_components_are_bytes(self):
        for color in Color:
            rgb_tuple = hex2rgb(color.rgb)
            assert len(rgb_tuple) == 3
            assert all(isinstance(c, int) and 0 <= c <= 255 for c in rgb_tuple)


class TestLinearRgb:
    def test_black_and_white_are_fixed_points(self):
        assert linear_rgb("000000") == (0, 0, 0)
        assert linear_rgb("FFFFFF") == pytest.approx((1, 1, 1))

    def test_dark_channels_use_the_linear_segment(self):
        assert linear_rgb("0A0000")[0] == pytest.approx(10 / 255 / 12.92)

    def test_mid_grey_is_darker_in_linear_light(self):
        assert linear_rgb("808080") == pytest.approx((0.2158605,) * 3)


class TestFinish:
    def test_every_finish_has_a_display_name_and_description(self):
        for finish in Finish:
            assert finish.display_name.strip()
            assert finish.__doc__ and finish.__doc__.strip()


class TestPalette:
    def test_color_attributes(self):
        assert Color.RED.lego_id == 21
        assert Color.RED.ldraw_id == 4
        assert Color.RED.rgb == "C91A09"
        assert Color.RED.display_name == "Red"
        assert Color.DARK_BLUISH_GRAY.display_name == "Dark Bluish Gray"

    def test_lego_ids_are_unique(self):
        ids = [color.lego_id for color in Color]
        assert len(ids) == len(set(ids))

    def test_ldraw_ids_are_unique(self):
        ids = [color.ldraw_id for color in Color]
        assert len(ids) == len(set(ids))

    def test_every_color_has_a_finish(self):
        for color in Color:
            assert isinstance(color.finish, Finish)

    def test_sentinel_colors_carry_the_expected_finish(self):
        assert Color.RED.finish is Finish.SOLID
        assert Color.TRANS_RED.finish is Finish.TRANSPARENT
        assert Color.OPAL_TRANS_CLEAR.finish is Finish.OPALESCENT
        assert Color.GLITTER_TRANS_CLEAR.finish is Finish.GLITTER
        assert Color.CHROME_GOLD.finish is Finish.CHROME
        assert Color.PEARL_GOLD.finish is Finish.PEARL
        assert Color.METALLIC_SILVER.finish is Finish.METALLIC
        assert Color.GLOW_IN_DARK_WHITE.finish is Finish.GLOW

    def test_color_renders_as_bare_member(self):
        assert repr(Color.RED) == "Color.RED"
        assert repr(Color.DARK_BLUISH_GRAY) == "Color.DARK_BLUISH_GRAY"
