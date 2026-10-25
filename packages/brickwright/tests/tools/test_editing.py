"""Tests for the token-efficient str-replace editor."""

import pytest

from brickwright.tools.editing import (
    EditError,
    ViewError,
    apply_edits,
    edit_build,
    insert,
    insert_build,
    multi_edit_build,
    str_replace,
    view,
)
from brickwright.tools.schemas import EditBuildArgs


def _edits(*pairs: tuple[str, str]) -> list[EditBuildArgs]:
    return [EditBuildArgs(old_str=old, new_str=new) for old, new in pairs]


class TestView:
    def test_numbers_every_line(self):
        assert view("a\nb\n") == "1: a\n2: b"

    def test_a_trailing_newline_does_not_add_a_phantom_line(self):
        assert view("a\nb\n").count("\n") == 1  # two display lines, one separator

    def test_right_aligns_numbers_to_the_widest(self):
        text = "\n".join(f"l{i}" for i in range(1, 11)) + "\n"
        lines = view(text).split("\n")
        assert lines[0] == " 1: l1"
        assert lines[9] == "10: l10"

    def test_view_range_slices_inclusively(self):
        assert view("a\nb\nc\nd\n", [2, 3]) == "2: b\n3: c"

    def test_end_of_minus_one_means_eof(self):
        assert view("a\nb\nc\n", [2, -1]) == "2: b\n3: c"

    def test_out_of_bounds_range_reports_the_valid_range(self):
        with pytest.raises(ViewError, match=r"1\.\.3"):
            view("a\nb\nc\n", [1, 9])

    def test_start_after_end_is_rejected(self):
        with pytest.raises(ViewError):
            view("a\nb\nc\n", [3, 2])

    def test_start_below_one_is_rejected(self):
        with pytest.raises(ViewError):
            view("a\nb\nc\n", [0, 2])


class TestInsertBuild:
    def test_inserts_and_returns_a_snippet(self, record):
        record.write_build("l1\nl2\n")
        snippet = insert_build(record, 1, "NEW")
        assert record.read_build() == "l1\nNEW\nl2\n"
        assert "2: NEW" in snippet

    def test_failed_insert_leaves_the_file_untouched(self, record):
        record.write_build("original\n")
        with pytest.raises(EditError):
            insert_build(record, 99, "x")
        assert record.read_build() == "original\n"


class TestEditBuild:
    def test_applies_the_edit_to_build_py(self, record):
        record.write_build("def build():\n    return 1\n")
        edit_build(record, "return 1", "return 2")
        assert record.read_build() == "def build():\n    return 2\n"

    def test_failed_edit_leaves_the_file_untouched(self, record):
        record.write_build("original\n")
        with pytest.raises(EditError):
            edit_build(record, "absent", "x")
        assert record.read_build() == "original\n"

    def test_returns_a_numbered_snippet_of_the_edited_region(self, record):
        record.write_build("l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\nl11\n")
        snippet = edit_build(record, "l6", "CHANGED")
        lines = snippet.split("\n")
        assert lines[0].strip() == "2: l2"  # 4 lines of context above
        assert " 6: CHANGED" in snippet
        assert lines[-1].strip() == "10: l10"  # 4 lines of context below

    def test_snippet_is_clamped_at_the_file_edges(self, record):
        record.write_build("l1\nl2\n")
        snippet = edit_build(record, "l1", "CHANGED")
        assert snippet == "1: CHANGED\n2: l2"

    def test_replace_all_is_forwarded(self, record):
        record.write_build("a\na\n")
        edit_build(record, "a", "b", replace_all=True)
        assert record.read_build() == "b\nb\n"


class TestMultiEditBuild:
    def test_applies_the_batch_and_reports_the_count(self, record):
        record.write_build("a\nb\n")
        applied = multi_edit_build(
            record,
            _edits(("a", "x"), ("b", "y")),
        )
        assert applied == 2
        assert record.read_build() == "x\ny\n"

    def test_atomic_rollback_on_a_late_failure(self, record):
        record.write_build("a\nb\n")
        with pytest.raises(EditError, match="edit 2 of 2"):
            multi_edit_build(
                record,
                _edits(("a", "x"), ("zzz", "y")),
            )
        assert record.read_build() == "a\nb\n"  # edit 1 was NOT applied


class TestInsert:
    def test_inserts_at_the_top_with_line_zero(self):
        assert insert("a\nb\n", 0, "x") == "x\na\nb\n"

    def test_inserts_after_the_given_line(self):
        assert insert("a\nb\n", 1, "x") == "a\nx\nb\n"

    def test_inserts_at_the_end(self):
        assert insert("a\nb\n", 2, "x") == "a\nb\nx\n"

    def test_appends_cleanly_when_the_file_lacks_a_trailing_newline(self):
        assert insert("a\nb", 2, "x") == "a\nb\nx"

    def test_trailing_newline_on_the_block_does_not_leave_a_blank_line(self):
        assert insert("a\n", 1, "x\ny\n") == "a\nx\ny\n"

    def test_multiline_block_without_trailing_newline(self):
        assert insert("a\n", 1, "x\ny") == "a\nx\ny\n"

    def test_line_out_of_range_reports_the_valid_range(self):
        with pytest.raises(EditError, match=r"0\.\.2"):
            insert("a\nb\n", 5, "x")

    def test_negative_line_is_rejected(self):
        with pytest.raises(EditError):
            insert("a\nb\n", -1, "x")

    def test_empty_text_is_rejected(self):
        with pytest.raises(EditError, match="empty"):
            insert("a\n", 1, "")


class TestStrReplace:
    def test_replaces_a_unique_occurrence(self):
        assert str_replace("a b c", "b", "B") == "a B c"

    def test_replaces_only_the_matched_span(self):
        assert str_replace("x = 1\ny = 2\n", "y = 2", "y = 99") == "x = 1\ny = 99\n"

    def test_replace_all_replaces_every_occurrence(self):
        assert str_replace("a a a", "a", "b", replace_all=True) == "b b b"

    def test_replace_all_with_a_single_occurrence_is_fine(self):
        assert str_replace("a b", "a", "c", replace_all=True) == "c b"

    def test_empty_old_str_raises(self):
        with pytest.raises(EditError, match="insert_build|write_build"):
            str_replace("abc", "", "x")

    def test_ambiguous_error_lists_the_occurrence_lines(self):
        with pytest.raises(EditError, match=r"lines 1, 3"):
            str_replace("x = 1\ny = 2\nx = 1\n", "x = 1", "x = 9")

    def test_ambiguous_error_suggests_replace_all(self):
        with pytest.raises(EditError, match="replace_all"):
            str_replace("a a", "a", "b")

    def test_noop_replacement_raises(self):
        with pytest.raises(EditError):
            str_replace("abc", "b", "b")


class TestStrReplaceWhitespaceTolerant:
    def test_uniformly_dedented_old_str_matches_and_reindents(self):
        text = "class C:\n    def f(self):\n        return 1\n"
        out = str_replace(
            text, "def f(self):\n    return 1", "def f(self):\n    return 2"
        )
        assert out == "class C:\n    def f(self):\n        return 2\n"

    def test_wrong_indent_kind_still_matches(self):
        text = "  a = 1\n"
        assert str_replace(text, "\ta = 1", "\ta = 2") == "  a = 2\n"

    def test_replacement_keeps_extra_relative_depth(self):
        text = "    if x:\n        y()\n"
        out = str_replace(text, "if x:\n    y()", "if x:\n    y()\n    z()")
        assert out == "    if x:\n        y()\n        z()\n"

    def test_ambiguous_normalized_match_is_an_error(self):
        text = "  a = 1\nb\n    a = 1\n"
        with pytest.raises(EditError, match="lines 1, 3"):
            str_replace(text, "\ta = 1", "a = 2")

    def test_replace_all_reindents_each_occurrence_to_its_own_line(self):
        text = "  a = 1\nb\n    a = 1\n"
        out = str_replace(text, "\ta = 1", "\ta = 9", replace_all=True)
        assert out == "  a = 9\nb\n    a = 9\n"

    def test_deleting_whole_lines_leaves_no_blank_line(self):
        # As an exact match of "    b = 2\n" would, the line goes entirely.
        assert str_replace("a\n    b = 2\nc\n", "\tb = 2\n", "") == "a\nc\n"

    def test_exact_match_still_wins_over_normalized(self):
        # "b" appears exactly once; the normalized tier must not run at all.
        assert str_replace("a\nb\n", "b", "c") == "a\nc\n"


class TestStrReplaceNoMatch:
    def test_reports_not_found(self):
        with pytest.raises(EditError, match="not found"):
            str_replace("a\nb\n", "zzz", "x")

    def test_echoes_the_closest_region_with_line_numbers(self):
        text = "def build():\n    bricks = 4\n    return bricks\n"
        with pytest.raises(EditError) as excinfo:
            str_replace(text, "bricks = 5", "bricks = 6")
        message = str(excinfo.value)
        assert "bricks = 4" in message
        assert "2:" in message  # the near-miss line, numbered

    def test_flags_pasted_line_number_prefixes(self):
        with pytest.raises(EditError, match="display-only"):
            str_replace("alpha\nbeta\n", "1: alpha", "gamma")

    def test_no_misleading_region_for_garbage(self):
        with pytest.raises(EditError) as excinfo:
            str_replace("a\nb\n", "qqqqqq zzzzzz wwwww", "x")
        assert "losest" not in str(excinfo.value)  # no "Closest match" section

    def test_the_input_text_is_not_needed_to_be_modified(self):
        # Pure function: a failed replace returns nothing and raises; callers
        # (Task 7) rely on the raise happening before any write.
        text = "a\nb\n"
        with pytest.raises(EditError):
            str_replace(text, "zzz", "x")
        assert text == "a\nb\n"


class TestApplyEdits:
    def test_applies_edits_in_order_and_later_edits_see_earlier_results(self):
        edits = _edits(("a", "b"), ("b", "c"))  # "b" only exists after edit 1
        assert apply_edits("a\n", edits) == "c\n"

    def test_a_failing_edit_names_its_position(self):
        edits = _edits(("a", "b"), ("zzz", "x"))
        with pytest.raises(EditError, match="edit 2 of 2"):
            apply_edits("a\n", edits)

    def test_replace_all_inside_a_batch(self):
        edits = [EditBuildArgs(old_str="a", new_str="b", replace_all=True)]
        assert apply_edits("a a\n", edits) == "b b\n"
