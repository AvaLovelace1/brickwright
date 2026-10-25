"""Tests for the part-popularity extraction script."""

import csv
import gzip
import io
from pathlib import Path

from bricklayer.ldraw.scripts import extract_part_popularity as extract


def _write_gzip_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    with gzip.open(path, "wt", newline="") as f:
        f.write(buffer.getvalue())


_INVENTORY_PARTS_FIELDS = [
    "inventory_id",
    "part_num",
    "color_id",
    "quantity",
    "is_spare",
    "img_url",
]


class TestCandidateIds:
    def test_tries_the_id_itself_first(self):
        assert next(extract.candidate_ids("3001")) == "3001"

    def test_a_plain_id_has_no_fallback(self):
        assert list(extract.candidate_ids("3001")) == ["3001"]

    def test_falls_back_to_the_base_id_without_its_variant_letter(self):
        # 3069a/3069b are LDraw's grooved/ungrooved split of Rebrickable's 3069.
        assert list(extract.candidate_ids("3069b")) == ["3069b", "3069"]

    def test_falls_back_to_the_id_without_its_pattern_suffix(self):
        # 3069bp01's pattern-stripped base (3069b) still carries a variant
        # letter, so it is tried both as-is and with that letter stripped too.
        assert list(extract.candidate_ids("3069bp01")) == [
            "3069bp01",
            "3069b",
            "3069",
        ]

    def test_falls_back_to_the_id_without_its_composite_suffix(self):
        assert list(extract.candidate_ids("4079c01")) == ["4079c01", "4079"]


class TestScoreParts:
    def test_scores_a_direct_match(self):
        assert extract.score_parts(["3001"], {"3001": 9000}) == {"3001": 9000}

    def test_falls_back_through_the_candidate_chain(self):
        assert extract.score_parts(["3069bp01"], {"3069b": 42}) == {"3069bp01": 42}

    def test_falls_back_past_a_pattern_suffix_to_the_bare_variant(self):
        # Rebrickable has no entry for 3069b itself, only the bare 3069.
        assert extract.score_parts(["3069bp01"], {"3069": 42}) == {"3069bp01": 42}

    def test_an_unscored_id_is_omitted_not_zeroed(self):
        # popularity() supplies the 0 default; the extractor only ever writes
        # ids it actually scored.
        assert extract.score_parts(["ghost"], {}) == {}


class TestLoadInventorySets:
    def test_maps_inventory_id_to_set_number(self, tmp_path):
        path = tmp_path / "inventories.csv.gz"
        _write_gzip_csv(
            path,
            ["id", "version", "set_num"],
            [
                {"id": "1", "version": "1", "set_num": "7922-1"},
                {"id": "2", "version": "1", "set_num": "3931-1"},
            ],
        )
        assert extract.load_inventory_sets(path) == {"1": "7922-1", "2": "3931-1"}


class TestSetsPerPart:
    def test_dedupes_multiple_rows_of_the_same_part_in_one_set(self, tmp_path):
        # Two colors of 3001 in inventory 1: one set, counted once.
        path = tmp_path / "inventory_parts.csv.gz"
        _write_gzip_csv(
            path,
            _INVENTORY_PARTS_FIELDS,
            [
                {
                    "inventory_id": "1",
                    "part_num": "3001",
                    "color_id": "0",
                    "quantity": "2",
                    "is_spare": "False",
                    "img_url": "",
                },
                {
                    "inventory_id": "1",
                    "part_num": "3001",
                    "color_id": "1",
                    "quantity": "1",
                    "is_spare": "False",
                    "img_url": "",
                },
                {
                    "inventory_id": "2",
                    "part_num": "3001",
                    "color_id": "0",
                    "quantity": "1",
                    "is_spare": "False",
                    "img_url": "",
                },
            ],
        )
        inventory_sets = {"1": "7922-1", "2": "3931-1"}
        assert extract.sets_per_part(path, inventory_sets) == {
            "3001": {"7922-1", "3931-1"}
        }

    def test_ignores_a_row_whose_inventory_is_unknown(self, tmp_path):
        path = tmp_path / "inventory_parts.csv.gz"
        _write_gzip_csv(
            path,
            _INVENTORY_PARTS_FIELDS,
            [
                {
                    "inventory_id": "99",
                    "part_num": "3001",
                    "color_id": "0",
                    "quantity": "1",
                    "is_spare": "False",
                    "img_url": "",
                }
            ],
        )
        assert extract.sets_per_part(path, {}) == {}


class TestFetch:
    def test_skips_the_download_when_already_cached(self, tmp_path, monkeypatch):
        cached = tmp_path / "inventories.csv.gz"
        cached.write_bytes(b"cached")
        calls = []
        monkeypatch.setattr(
            extract.urllib.request,
            "urlretrieve",
            lambda *args, **kwargs: calls.append(args),
        )
        assert extract.fetch("inventories.csv.gz", tmp_path) == cached
        assert calls == []

    def test_downloads_when_not_cached(self, tmp_path, monkeypatch):
        calls = []

        def fake_urlretrieve(url, filename):
            calls.append(url)
            Path(filename).write_bytes(b"downloaded")

        monkeypatch.setattr(extract.urllib.request, "urlretrieve", fake_urlretrieve)
        result = extract.fetch("inventories.csv.gz", tmp_path)
        assert calls == [f"{extract._BASE_URL}/inventories.csv.gz"]
        assert result.read_bytes() == b"downloaded"
