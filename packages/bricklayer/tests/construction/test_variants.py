"""Tests for the variant enums."""

from bricklayer.construction import VARIANT_ENUMS


class TestVariants:
    def test_every_variant_member_has_its_own_doc(self):
        for variant_type in VARIANT_ENUMS:
            for variant in variant_type:
                assert variant.__doc__ and variant.__doc__.strip()
                assert variant.__doc__ != variant_type.__doc__

    def test_every_variant_renders_as_a_bare_member(self):
        for variant_type in VARIANT_ENUMS:
            for variant in variant_type:
                assert repr(variant) == f"{variant_type.__name__}.{variant.name}"
