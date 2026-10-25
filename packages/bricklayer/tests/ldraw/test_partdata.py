"""Tests for LDraw part records, taxonomy, and data loading."""

import json
from pathlib import Path

import pytest

from bricklayer import Cuboid, Pose, Position, Rotation
from bricklayer.geometry.connections import same_connector
from bricklayer.geometry.linalg import vec_max, vec_min
from bricklayer.ldraw import partdata
from bricklayer.ldraw.connectivity import ConnectorRaw
from bricklayer.ldraw.conversion import LDrawVec
from bricklayer.ldraw.partdata import PartRecord, part_ids, record
from bricklayer.parts.catalog import Chirality, all_parts

_DATA_DIR = Path(partdata.__file__).parent

# A pitch that tips a connector onto its side (its axis points along the depth
# axis rather than up), so it is not upward-facing.
_SIDEWAYS_PITCH = 90.0


def _stud_row(
    pos: tuple[float, float, float],
    num: int,
    *,
    anti: bool = False,
    pitch: float = 0.0,
) -> tuple[ConnectorRaw, ...]:
    """``num`` stud connectors one stud (20 LDU) apart along +x, from ``pos``.

    Studs face up unless ``pitch`` tips them.
    """
    return tuple(
        ConnectorRaw(
            type="antistud" if anti else "stud",
            pos=(pos[0] + 20.0 * i, pos[1], pos[2]),
            pitch=pitch,
        )
        for i in range(num)
    )


def _collider_bbox(part_id: str) -> tuple[Position, Position]:
    """A part's collision-mesh bounds, mapped from the raw LDU frame that
    ``PartRecord.collider`` is kept in into the same element frame as
    ``bounding_box``, so the two can be compared."""
    rec = record(part_id)
    # LDraw's height axis is inverted, so the converted corners need re-ordering.
    corners = [
        LDrawVec(*rec.collider.lo).to_position(),
        LDrawVec(*rec.collider.hi).to_position(),
    ]
    box = Cuboid.spanning(vec_min(corners), vec_max(corners))
    return box.transformed(rec.ldraw_to_element_pose).aabb


class TestPartRecord:
    def test_offset_defaults_to_zero(self):
        rec = PartRecord("x", _bbox=(LDrawVec(-10, -4, -20), LDrawVec(30, 24, 60)))
        assert rec.offset == Position(0, 0, 0)
        corners = (
            LDrawVec(-10, -4, -20).to_position(),
            LDrawVec(30, 24, 60).to_position(),
        )
        assert rec.bounding_box == (vec_min(corners), vec_max(corners))

    def test_unmeasured_record_is_all_zero(self):
        rec = PartRecord("x")
        # Without a bounding box or grid connectors, the offset and dimensions are all zero.
        assert rec.bounding_box == (Position(0, 0, 0), Position(0, 0, 0))
        assert rec.offset == Position(0, 0, 0)

    def test_offset_recenters_an_off_center_footprint(self):
        # A single top row whose footprint centers at x=+10 LDU and sits one brick
        # up: the offset moves the box bottom-center onto the origin.
        rec = PartRecord("x", _connectors=_stud_row((0, -24, 0), 2))
        assert rec.offset == LDrawVec(-10, 24, 0).to_position()

    def test_offset_seats_the_grid_footprint_over_a_measured_bbox(self):
        rec = PartRecord(
            "x",
            _bbox=(LDrawVec(-40, -4, -20), LDrawVec(40, 24, 20)),
            _connectors=_stud_row((0, -24, 0), 2),
        )
        # The offset seats the grid footprint's bottom-center on the origin,
        # independent of the measured bounding box.
        assert rec.offset == LDrawVec(-10, 24, 0).to_position()
        corners = (
            LDrawVec(-40, -4, -20).to_position() + rec.offset,
            LDrawVec(40, 24, 20).to_position() + rec.offset,
        )
        assert rec.bounding_box == (
            pytest.approx(vec_min(corners)),
            pytest.approx(vec_max(corners)),
        )

    def test_grid_connectors_define_a_box_centered_on_their_footprint(self):
        # Top studs and bottom antistuds one stud apart, centered on x=0: a
        # 2x1x1 alignment box (40 wide, 24 tall, 20 deep) centered on the origin.
        rec = PartRecord(
            "x",
            _connectors=(
                *_stud_row((-10, -24, 0), 2),
                *_stud_row((-10, 0, 0), 2, anti=True),
            ),
        )
        assert rec.offset == Position(0, 0, 0)

    def test_only_upward_grid_connectors_count(self):
        # A sideways grid is not upward-facing, so it never reaches the alignment
        # box (this record has no bounding box, so the box stays degenerate).
        rec = PartRecord(
            "x", _connectors=_stud_row((0, 0, 0), 2, pitch=_SIDEWAYS_PITCH)
        )
        assert rec.offset == Position(0, 0, 0)

    def test_non_grid_connectors_are_ignored(self):
        # A connector outside the stud and hole families contributes nothing.
        rec = PartRecord("x", _connectors=(ConnectorRaw(type="clip", pos=(5, 5, 5)),))
        assert rec.offset == Position(0, 0, 0)

    def test_authored_override_connector_seats_the_offset(self):
        # An authored connector written with named axis/side facings seats the
        # alignment box like any other, and decodes shifted by that offset.
        rec = PartRecord(
            "x",
            _connectors=(
                ConnectorRaw(type="antistud", pos=(0, -24, 0), axis="UP", side="LEFT"),
            ),
        )
        assert rec.offset == LDrawVec(0, 24, 0).to_position()
        (connector,) = rec.connectors
        assert connector.type.name == "antistud"
        assert connector.position == LDrawVec(0, 0, 0).to_position()


class TestOffsetRotation:
    _FLIP = Pose.from_rotation(Rotation.DEG_180)

    def _pair(self, **raw) -> tuple[PartRecord, PartRecord]:
        """A ``(flat, flipped)`` record pair sharing the same raw ``raw`` data."""
        return (
            PartRecord("x", **raw),
            PartRecord("x", offset_rotation=Rotation.DEG_180.matrix, **raw),
        )

    def test_defaults_to_no_turn(self):
        assert PartRecord.from_raw("x", {}).offset_rotation == Rotation.DEG_0.matrix

    def test_is_read_from_the_raw_record_by_name(self):
        rec = PartRecord.from_raw("x", {"offset_rotation": "DEG_90"})
        assert rec.offset_rotation == Rotation.DEG_90.matrix

    def test_offset_is_unchanged_by_the_turn(self):
        # The offset seats the raw part before the turn, so it is turn-independent.
        flat, flipped = self._pair(_connectors=_stud_row((0, -24, 0), 2))
        assert flipped.offset == flat.offset == LDrawVec(-10, 24, 0).to_position()

    def test_connectors_are_seated_then_turned(self):
        flat, flipped = self._pair(_connectors=_stud_row((0, -24, 0), 2))
        assert all(
            same_connector(turned, seated.transformed(self._FLIP))
            for turned, seated in zip(flipped.connectors, flat.connectors, strict=True)
        )
        # The turn genuinely moves the off-center connectors, not a no-op.
        assert any(
            not same_connector(turned, seated)
            for turned, seated in zip(flipped.connectors, flat.connectors)
        )

    def test_bounding_box_is_seated_then_turned(self):
        # An off-center box (in width and depth) so the half-turn actually moves it.
        box = {"_bbox": (LDrawVec(-10, -4, -20), LDrawVec(30, 24, 60))}
        flat, flipped = self._pair(**box)
        want_lo, want_hi = (
            Cuboid.spanning(*flat.bounding_box).transformed(self._FLIP).aabb
        )
        got_lo, got_hi = flipped.bounding_box
        assert tuple(got_lo) == pytest.approx(tuple(want_lo))
        assert tuple(got_hi) == pytest.approx(tuple(want_hi))
        assert flipped.bounding_box != flat.bounding_box  # the box genuinely moved


class TestPartBoundingBox:
    def test_brick_bbox_sits_on_the_ground_and_includes_the_stud(self):
        # 3005 is a 1x1x1 brick: its physical bounding box sits with its
        # bottom on the ground and its top raised by the stud protrusion.
        lo, hi = record("3005").bounding_box
        assert lo == Position(-0.5, -0.5, 0)
        # 1 brick tall plus the stud (~4 LDU = 1/6 brick).
        assert hi.x == pytest.approx(0.5)
        assert hi.y == pytest.approx(0.5)
        assert hi.z == pytest.approx(1 + 1 / 6)

    def test_is_independent_of_the_inset_collision_mesh(self):
        # The physical bbox reaches the full footprint (+/-0.5), while the inset
        # collision mesh stops short of it.
        lo, hi = record("3005").bounding_box
        collider_lo, collider_hi = _collider_bbox("3005")
        assert hi.x > collider_hi.x
        assert lo.z < collider_lo.z


class TestRecordLookup:
    def test_known_part_has_measured_bbox(self):
        # 3001 is a 4x2 brick, measured in part_geometry.json.
        assert record("3001").ldraw_bounds is not None

    def test_unknown_part_returns_empty_record(self):
        rec = record("nonexistent-part")
        assert rec == PartRecord("nonexistent-part")


class TestLazyLoading:
    def test_reading_one_part_does_not_validate_every_part(self, monkeypatch):
        """The connectivity file covers the whole BrickNet library, so eagerly
        validating it would cost seconds of import time for data nobody touched."""
        from bricklayer.ldraw import partdata

        partdata.record.cache_clear()
        validated = []
        original = partdata._RawRecord.model_validate

        def counting(raw, *args, **kwargs):
            validated.append(raw)
            return original(raw, *args, **kwargs)

        monkeypatch.setattr(partdata._RawRecord, "model_validate", counting)
        assert partdata.record("3001").connectors
        assert len(validated) == 1


class TestMeasuredExtents:
    """``measured_extents`` must answer exactly what ``bounding_box``'s
    hi-lo difference would, without needing the connector geometry
    ``offset`` (a pure translation) decodes to compute -- see
    :func:`bricklayer.parts.derivation._misreads_measured_geometry`,
    its only caller."""

    def test_unmeasured_record_is_zero(self):
        assert PartRecord("x").measured_extents == Position(0, 0, 0)

    def test_equals_bounding_box_hi_minus_lo_for_an_unturned_part(self):
        rec = PartRecord("x", _bbox=(LDrawVec(-10, -4, -20), LDrawVec(30, 24, 60)))
        lo, hi = rec.bounding_box
        assert rec.measured_extents == pytest.approx(hi - lo)

    def test_is_independent_of_a_grid_driven_offset(self):
        # Same measured bbox, but an off-center grid footprint gives one
        # record a nonzero offset -- the extents must not depend on it.
        bbox = (LDrawVec(-40, -4, -20), LDrawVec(40, 24, 20))
        centered = PartRecord("x", _bbox=bbox)
        off_center = PartRecord("x", _bbox=bbox, _connectors=_stud_row((0, -24, 0), 2))
        assert centered.offset != off_center.offset
        assert centered.measured_extents == pytest.approx(off_center.measured_extents)

    def test_is_turned_like_the_bounding_box(self):
        # A 90-degree turn swaps x and y, for both the box and the extents.
        bbox = (LDrawVec(-10, -4, -20), LDrawVec(30, 24, 60))
        flat = PartRecord("x", _bbox=bbox)
        turned = PartRecord("x", _bbox=bbox, offset_rotation=Rotation.DEG_90.matrix)
        assert turned.measured_extents == pytest.approx(
            Position(
                flat.measured_extents.y,
                flat.measured_extents.x,
                flat.measured_extents.z,
            )
        )


class TestGeometryQuestionsNeverLoadConnectivity:
    """Neither ``part_ids()`` nor ``measured_extents()`` -- and so no
    ``import bricklayer``, membership check or shape derivation -- may pay to
    parse BrickNet's 9.5 MB ``part_connectivity.json``. An id, a ``bbox`` and
    an ``offset_rotation`` all live in the small geometry files. Only
    :func:`record`, for the one id it was actually asked about, pulls
    connectivity in."""

    @pytest.fixture
    def no_connectivity(self, monkeypatch):
        """Fail the test if a connectivity file is loaded, with the geometry
        caches dropped either side so the load actually has to happen."""
        caches = (partdata.part_ids, partdata.measured_extents)
        for cache in caches:
            cache.cache_clear()
        original = partdata._load_data_file

        def guarded(name):
            assert name not in (
                "part_connectivity.json",
                "part_connectivity_overrides.json",
            ), f"a geometry question must not load {name}"
            return original(name)

        monkeypatch.setattr(partdata, "_load_data_file", guarded)
        yield
        for cache in caches:
            cache.cache_clear()

    def test_membership_never_loads_the_connectivity_files(self, no_connectivity):
        assert partdata.part_ids()

    def test_measured_extents_never_loads_the_connectivity_files(self, no_connectivity):
        assert partdata.measured_extents("3001") != Position(0, 0, 0)

    def test_measured_extents_matches_the_full_record(self):
        """The cheap path must answer exactly what the full merge would, which
        holds only while every input to it -- ``bbox`` and ``offset_rotation``
        -- sits in the geometry files. Checked over every part that carries an
        ``offset_rotation``, because those are precisely the ones a geometry
        merge missing that file would silently measure unturned."""
        turned = partdata._load_data_file("part_offset_rotations.json")["parts"]
        assert turned, "no offset-rotated parts left to check"
        for part_id in (*turned, "3001", "3020"):
            expected = record(part_id).measured_extents
            assert partdata.measured_extents(part_id) == expected, part_id

    def test_an_unknown_part_measures_zero(self):
        assert partdata.measured_extents("not-a-part") == Position(0, 0, 0)

    def test_record_still_carries_connectivity(self):
        # record() is where connectivity actually gets pulled in.
        assert record("3001").connectors


class TestCatalogCoverage:
    def test_every_catalogued_part_has_a_measured_bounding_box(self):
        """An unmeasured part yields an empty record, and so an element with a
        degenerate box -- silently, since ``record`` answers for any id.

        Membership itself is defined by having measured geometry (see
        ``partdata.part_ids()``), so this should hold vacuously; a failure here
        means that definition and this coverage sweep have drifted apart.
        """
        unmeasured = {
            part_id for part_id in part_ids() if record(part_id).ldraw_bounds is None
        }
        assert unmeasured == set()

    @pytest.mark.parametrize("part_id", ["72824", "54821", "52629", "86500"])
    def test_connectorless_parts_have_geometry_and_colliders(self, part_id):
        assert part_id in part_ids()
        assert not record(part_id).connectors
        assert record(part_id).ldraw_bounds is not None
        assert len(record(part_id).collision_mesh.faces)

    @pytest.mark.parametrize(
        ("part_id", "donor"), [("3816b", "3816c"), ("3817b", "3817c")]
    )
    def test_obsolete_legs_recover_connector_frames(self, part_id, donor):
        raw = partdata._parts("part_connectivity.json")[part_id]
        assert raw["_source"] == donor
        assert {c.type for c in record(part_id).connectors} == {
            c.type for c in record(donor).connectors
        }

    @pytest.mark.parametrize(
        ("part_id", "expected"),
        [
            ("3626bp01", "pin_hole"),  # minifig head
            ("30124b", "visor_socket"),  # minifig helmet
            ("86210", "hinge_18_in"),  # glass for window 1x4x3
        ],
    )
    def test_canonical_parts_carry_their_connectors(self, part_id, expected):
        names = {c.type.name for c in record(part_id).connectors}
        assert expected in names


class TestTaxonomy:
    def test_every_catalogued_part_resolves_to_a_real_ldraw_name(self) -> None:
        """Redirects resolve to descriptions and other parts retain their names."""
        unresolved = [
            pid
            for pid in partdata.part_ids()
            if (taxon := partdata.taxonomy(pid)) is None
            or not taxon.name
            or "Moved to" in taxon.name
        ]
        assert unresolved == []

    def test_taxonomy_file_is_sorted_and_committed(self) -> None:
        data = json.loads((_DATA_DIR / "part_taxonomy.json").read_text())["parts"]
        assert list(data) == sorted(data)

    def test_a_handed_part_wears_its_handedness_in_its_ldraw_name(self) -> None:
        """Chirality is derived, not curated, so the name is the only evidence for
        it: every part the catalog reports as handed must say so in its name."""
        handed = [
            (spec, chirality)
            for spec in all_parts()
            if (chirality := spec.chirality) is not None
        ]
        assert handed
        for spec, chirality in handed:
            assert chirality.display_name in spec.name

    def test_a_descriptive_handedness_word_is_not_read_as_handedness(self) -> None:
        """A name can wear "Left"/"Right" descriptively rather than as a handedness:
        hair swept left, a staircase turning left, a left hair parting. Chirality is
        derived from the word's *position*, so those parts report no handedness --
        and because the derivation never edits the name, the word stays visible in
        whichever zone owns it instead of being eaten out of both.

        Driven from the catalog rather than from a list of ids, so a part added
        later tests itself.
        """
        descriptive = [
            spec
            for spec in all_parts()
            if spec.chirality is None
            and any(hand.display_name in spec.name for hand in Chirality)
        ]
        assert descriptive
        for spec in descriptive:
            zones = " ".join(filter(None, (spec.subcategory, spec.features)))
            assert any(hand.display_name in zones for hand in Chirality), spec.ldraw_id


class TestTaxonomyParsesLazily:
    """Taxonomy parsing is cached per id; membership queries need no parsing."""

    @pytest.fixture
    def parses(self, monkeypatch):
        """The descriptions ``parse_description`` was called with, live."""
        calls = []
        original = partdata.parse_description

        def counting(description):
            calls.append(description)
            return original(description)

        monkeypatch.setattr(partdata, "parse_description", counting)
        partdata.taxonomy.cache_clear()
        yield calls
        partdata.taxonomy.cache_clear()

    def test_a_description_is_parsed_once_per_id(self, parses):
        for _ in range(3):
            assert partdata.taxonomy("3001") is not None
        assert len(parses) == 1

    def test_membership_parses_no_description_at_all(self, parses, monkeypatch):
        partdata.part_ids.cache_clear()
        try:
            assert len(partdata.part_ids()) > 10_000
        finally:
            partdata.part_ids.cache_clear()
        assert parses == []


class TestTaxonomyParseErrors:
    """A bad row must name its part id, not surface far from its cause
    (see :func:`bricklayer.ldraw.partdata.taxonomy`)."""

    @pytest.fixture(autouse=True)
    def _fresh_taxonomy_caches(self):
        """Drop what the real data file cached, before and after: this class
        swaps that file out, so a warm entry either way would answer for the
        wrong descriptions."""
        for clear in (partdata._parts, partdata.taxonomy):
            clear.cache_clear()
        yield
        for clear in (partdata._parts, partdata.taxonomy):
            clear.cache_clear()

    def _patch_taxonomy_file(self, monkeypatch, parts):
        original = partdata._load_data_file

        def patched(name):
            if name == "part_taxonomy.json":
                return {"parts": parts}
            return original(name)

        monkeypatch.setattr(partdata, "_load_data_file", patched)

    def test_a_description_that_fails_to_parse_names_its_part_id(self, monkeypatch):
        self._patch_taxonomy_file(monkeypatch, {"bad-part": "whatever"})

        def failing(desc):
            raise ValueError("boom")

        monkeypatch.setattr(partdata, "parse_description", failing)
        with pytest.raises(ValueError, match="bad-part"):
            partdata.taxonomy("bad-part")


class TestPopularity:
    def test_a_common_part_scores_far_above_a_rare_one(self) -> None:
        """Popularity orders parts by how many sets contain them, which is what
        makes search put the brick you meant above a variant you have never
        seen. Driven from the two extremes rather than pinned values, so a data
        refresh does not break it."""
        scored = {
            spec.ldraw_id: partdata.popularity(spec.ldraw_id) for spec in all_parts()
        }
        assert max(scored.values()) > 1000
        common = max(scored, key=lambda pid: scored[pid])
        rare = min(scored, key=lambda pid: scored[pid])
        assert scored[common] > scored[rare]

    def test_an_unscored_part_is_zero_not_an_error(self) -> None:
        """Two thirds of the catalog is scored; the rest must rank last rather
        than raise, since an unscored part is still a real part."""
        assert partdata.popularity("definitely-not-a-part") == 0

    def test_every_catalogued_part_has_a_usable_score(self) -> None:
        for spec in all_parts():
            assert partdata.popularity(spec.ldraw_id) >= 0
