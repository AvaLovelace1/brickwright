"""Editing of a record's build.py."""

import difflib
import re

from ..record import Record
from .schemas import EditBuildArgs


class ViewError(ValueError):
    """Raised when a view range is invalid."""


class EditError(ValueError):
    """Raised when an edit cannot be applied unambiguously."""


# A read_build display line: optional indent, line number, colon, space.
_DISPLAY_PREFIX = re.compile(r"^\s*\d+: ")

# Best-window similarity below this is noise, not a near-miss worth echoing.
_CLOSEST_MATCH_FLOOR = 0.5

# Lines of context around an edited region in the echoed snippet.
_SNIPPET_CONTEXT = 4


def view(text: str, view_range: list[int] | None = None) -> str:
    """Render ``text`` with 1-indexed line-number prefixes, optionally sliced.

    ``view_range`` is a 1-indexed inclusive ``[start, end]``; ``end == -1``
    means end-of-file. The ``N: `` prefixes are display-only.

    Raises:
        ViewError: if ``view_range`` is malformed or out of bounds.
    """
    num = _num_lines(text)
    start, end = 1, num
    if view_range is not None:
        start, end = view_range
        if end == -1:
            end = num
        if not (1 <= start <= num and start <= end <= num):
            raise ViewError(
                f"invalid view_range {view_range}: the file has lines 1..{num} "
                f"(end may be -1 for end-of-file)"
            )
    lines = text.split("\n")[start - 1 : end]
    width = len(str(end))
    return "\n".join(f"{n:>{width}}: {line}" for n, line in enumerate(lines, start))


def insert_build(record: Record, insert_line: int, insert_text: str) -> str:
    """Insert text at a line boundary of a record's ``build.py``.

    Returns a line-numbered snippet of the inserted region; a failed insert
    leaves the file untouched.
    """
    before = record.read_build()
    updated = insert(before, insert_line, insert_text)
    record.write_build(updated)
    return _change_snippet(before, updated)


def edit_build(
    record: Record, old_str: str, new_str: str, replace_all: bool = False
) -> str:
    """Apply a str-replace to a record's ``build.py``.

    The file is only written when the replacement succeeds, so a failed edit
    leaves it untouched. Returns a line-numbered snippet of the edited region.
    """
    before = record.read_build()
    updated = str_replace(before, old_str, new_str, replace_all)
    record.write_build(updated)
    return _change_snippet(before, updated)


def multi_edit_build(record: Record, edits: list[EditBuildArgs]) -> int:
    """Apply a batch of edits to a record's ``build.py`` atomically.

    Nothing is written unless every edit succeeds. Returns how many were
    applied.
    """
    updated = apply_edits(record.read_build(), edits)
    record.write_build(updated)
    return len(edits)


def insert(text: str, insert_line: int, insert_text: str) -> str:
    """Insert ``insert_text`` at a line boundary of ``text``.

    ``insert_line`` 0 inserts before the first line; N inserts after line N.
    The block is inserted line-wise, so it can never fuse with the line below.

    Raises:
        EditError: if ``insert_line`` is out of range or ``insert_text`` is empty.
    """
    num = _num_lines(text)
    if not 0 <= insert_line <= num:
        raise EditError(
            f"invalid insert_line {insert_line}: must be in 0..{num} "
            f"(0 inserts at the top of the file; N inserts after line N)"
        )
    if not insert_text:
        raise EditError("insert_text is empty; nothing to insert")
    block = _split_lines(insert_text)
    lines = text.split("\n")
    return "\n".join(lines[:insert_line] + block + lines[insert_line:])


def str_replace(
    text: str, old_str: str, new_str: str, replace_all: bool = False
) -> str:
    """Replace ``old_str`` in ``text`` with ``new_str``.

    Matching ladder: exact match first; if ``old_str`` is absent exactly,
    fall back to a whitespace-tolerant line match; otherwise fail with an
    error rich enough to correct from. A fuzzy match is never auto-applied.

    Raises:
        EditError: if ``old_str`` is empty, equals ``new_str``, matches
            nothing, or matches more than once without ``replace_all``.
    """
    if not old_str:
        raise EditError(
            "old_str is empty; use insert_build to add new text or "
            "write_build to rewrite the file"
        )
    if old_str == new_str:
        raise EditError("old_str and new_str are identical; nothing to change")

    count = text.count(old_str)
    if count == 1 or (count > 1 and replace_all):
        return text.replace(old_str, new_str)
    if count > 1:
        at = ", ".join(str(n) for n in _occurrence_lines(text, old_str))
        raise EditError(
            f"old_str is not unique: it appears {count} times, at lines {at}. "
            f"Enlarge old_str with surrounding context to pin down one "
            f"occurrence, or pass replace_all=true to replace every occurrence."
        )
    return _whitespace_tolerant_replace(text, old_str, new_str, replace_all)


def apply_edits(text: str, edits: list[EditBuildArgs]) -> str:
    """Apply a batch of str-replace edits sequentially to ``text``.

    Later edits see earlier edits' results. Purely functional: on any
    failure the exception carries the 1-based index of the failing edit and
    the caller's original text is untouched.

    Raises:
        EditError: if any edit fails to match.
    """
    total = len(edits)
    for i, edit in enumerate(edits, start=1):
        try:
            text = str_replace(text, edit.old_str, edit.new_str, edit.replace_all)
        except EditError as exc:
            raise EditError(f"edit {i} of {total}: {exc}") from exc
    return text


def _occurrence_lines(text: str, needle: str) -> list[int]:
    """The 1-indexed line number where each occurrence of ``needle`` starts."""
    lines, idx = [], text.find(needle)
    while idx != -1:
        lines.append(text.count("\n", 0, idx) + 1)
        idx = text.find(needle, idx + len(needle))
    return lines


def _whitespace_tolerant_replace(
    text: str, old_str: str, new_str: str, replace_all: bool
) -> str:
    """Match ``old_str`` line-wise ignoring per-line indentation.

    On a unique (or ``replace_all``) match, ``new_str`` is re-indented by the
    first-line indentation delta between ``old_str`` and the matched block, so
    the file's real indentation is preserved.
    """
    lines = text.split("\n")
    old_block = _split_lines(old_str)
    new_block = _split_lines(new_str)
    if not new_str and old_str.endswith("\n"):
        new_block = []  # deleting whole lines, as an exact match would

    target = [line.strip() for line in old_block]
    n = len(target)
    stripped = [line.strip() for line in lines]
    starts = [i for i in range(len(lines) - n + 1) if stripped[i : i + n] == target]

    if not starts:
        raise _no_match_error(text, old_str)
    if len(starts) > 1 and not replace_all:
        at = ", ".join(str(i + 1) for i in starts)
        raise EditError(
            f"old_str matches {len(starts)} places once whitespace is "
            f"normalized, at lines {at}. Enlarge old_str with surrounding "
            f"context, or pass replace_all=true to replace every occurrence."
        )

    chosen, prev_end = [], -1
    for i in starts:  # replace_all: skip windows overlapping an earlier match
        if i >= prev_end:
            chosen.append(i)
            prev_end = i + n
    for i in reversed(chosen):
        block = _reindent(new_block, _leading_ws(old_block[0]), _leading_ws(lines[i]))
        lines[i : i + n] = block
    return "\n".join(lines)


def _no_match_error(text: str, old_str: str) -> EditError:
    """A not-found error rich enough for the model to self-correct."""
    parts = ["old_str not found."]
    if _looks_line_numbered(old_str):
        parts.append(
            "old_str looks like read_build output: the `N: ` line-number "
            "prefixes are display-only and must not be included in old_str."
        )
    region = _closest_region(text, old_str)
    if region is not None:
        start, end, snippet = region
        parts.append(f"Closest match, lines {start}-{end}:\n{snippet}")
    return EditError("\n".join(parts))


def _looks_line_numbered(old_str: str) -> bool:
    lines = [line for line in old_str.split("\n") if line.strip()]
    return bool(lines) and all(_DISPLAY_PREFIX.match(line) for line in lines)


def _closest_region(text: str, old_str: str) -> tuple[int, int, str] | None:
    """Locate the file region most similar to ``old_str``, for error messages.

    Returns ``(start_line, end_line, numbered_snippet)`` or ``None`` when
    nothing is similar enough to help.
    """
    lines = text.split("\n")
    old_lines = [line.strip() for line in old_str.split("\n") if line.strip()]
    if not old_lines:
        return None
    n = min(len(old_lines), len(lines))
    target = "\n".join(old_lines)
    stripped = [line.strip() for line in lines]
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(target)
    best_ratio, best_start = 0.0, 0
    for i in range(len(lines) - n + 1):
        matcher.set_seq1("\n".join(stripped[i : i + n]))
        if matcher.real_quick_ratio() <= best_ratio:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best_ratio, best_start = ratio, i
    if best_ratio < _CLOSEST_MATCH_FLOOR:
        return None
    start, end = best_start + 1, min(best_start + n, _num_lines(text))
    snippet = view(text, [max(1, start - 2), min(_num_lines(text), end + 2)])
    return start, end, snippet


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _reindent(lines: list[str], from_prefix: str, to_prefix: str) -> list[str]:
    """Swap ``from_prefix`` indentation for ``to_prefix`` on every line.

    Lines that don't carry ``from_prefix`` (or are blank) pass through
    unchanged -- better to leave unexpected indentation alone than to mangle it.
    """
    return [
        to_prefix + line[len(from_prefix) :]
        if line.strip() and line.startswith(from_prefix)
        else line
        for line in lines
    ]


def _change_snippet(before: str, after: str) -> str:
    """A numbered view of the region of ``after`` that differs from ``before``."""
    start, end = _changed_region(before, after)
    num = _num_lines(after)
    return view(
        after, [max(1, start - _SNIPPET_CONTEXT), min(num, end + _SNIPPET_CONTEXT)]
    )


def _changed_region(before: str, after: str) -> tuple[int, int]:
    """The 1-indexed inclusive line range of ``after`` that changed."""
    b, a = before.split("\n"), after.split("\n")
    start = 0
    while start < min(len(b), len(a)) and b[start] == a[start]:
        start += 1
    end_b, end_a = len(b), len(a)
    while end_b > start and end_a > start and b[end_b - 1] == a[end_a - 1]:
        end_b -= 1
        end_a -= 1
    return start + 1, max(end_a, start + 1)


def _split_lines(text: str) -> list[str]:
    """``text``'s lines, a trailing newline ending the last rather than adding one."""
    lines = text.split("\n")
    return lines[:-1] if len(lines) > 1 and lines[-1] == "" else lines


def _num_lines(text: str) -> int:
    """How many display lines ``text`` has (a trailing newline ends the last line)."""
    lines = text.split("\n")
    return len(lines) - 1 if text.endswith("\n") else len(lines)
