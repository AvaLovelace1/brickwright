"""Tests for choosing which LDraw parts the catalog holds."""

from bricklayer.ldraw.scripts.selection import select_part_ids


def test_a_part_needs_a_mesh_but_not_connectivity() -> None:
    selected = select_part_ids(
        mesh_ids=["a", "b"],
        descriptions={"a": "Brick  1 x  1", "b": "Brick  1 x  2", "c": "Brick  1 x  3"},
    )
    assert selected == ["a", "b"]


def test_marked_parts_with_colliders_are_importable() -> None:
    descriptions = {
        "obsolete": "~Brick  1 x  1 Superseded",
        "unofficial": "_Brick  1 x  1 Draft",
        "thirdparty": "| Hubelino Junction",
        "aliaswrapper": "=Brick  1 x  1 Alias",
        "good": "Brick  1 x  1",
    }
    selected = select_part_ids(
        mesh_ids=list(descriptions),
        descriptions=descriptions,
    )
    assert selected == sorted(descriptions)


def test_a_connectorless_ball_needs_no_exemption() -> None:
    selected = select_part_ids(
        mesh_ids=["72824"],
        descriptions={"72824": "Minifig Soccer Ball"},
    )
    assert selected == ["72824"]


def test_a_mesh_still_needs_a_description() -> None:
    selected = select_part_ids(mesh_ids=["ghost", "empty"], descriptions={"empty": ""})
    assert selected == []


def test_the_result_is_sorted_and_deduplicated() -> None:
    selected = select_part_ids(
        mesh_ids=["b", "a", "a"],
        descriptions={"a": "Brick  1 x  1", "b": "Brick  1 x  2"},
    )
    assert selected == ["a", "b"]
