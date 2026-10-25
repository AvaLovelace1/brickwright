"""Run a Python inspection snippet in a child process and capture its output."""

from __future__ import annotations

import ast
import io
import traceback
from contextlib import redirect_stdout

from pydantic import BaseModel, ConfigDict

from ..config import Config
from ..record import Record
from . import build_execution


class SnippetResult(BaseModel):
    """The outcome of one inspection snippet: did it run, and what it printed."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    output: str  # captured stdout on success; a labeled traceback on failure


def explore(record: Record, code: str, config: Config | None = None) -> SnippetResult:
    """Run ``code`` for inspection with ``bricklayer`` in scope.

    The record's build is created and bound to ``build`` only if ``code`` reads
    that name, so catalog lookups still run while build.py is broken. Runs in a child
    process under the build timeout.
    """
    config = config or Config()
    return build_execution.run_guarded(
        _explore,
        (str(record.build_path), code),
        config.build_timeout,
        lambda e: SnippetResult(ok=False, output=f"Explore failed: {e}"),
    )


def _explore(build_path: str, code: str) -> SnippetResult:
    scope = {}
    if _reads_build(code):
        try:
            scope["build"] = build_execution.create_build(build_path)
        except Exception:
            return SnippetResult(
                ok=False, output=f"build error:\n{traceback.format_exc()}"
            )
    return _run_snippet(code, scope)


def _reads_build(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False  # _run_snippet reports it
    return any(
        isinstance(node, ast.Name)
        and node.id == "build"
        and isinstance(node.ctx, ast.Load)
        for node in ast.walk(tree)
    )


def _run_snippet(code: str, scope: dict) -> SnippetResult:
    """Exec ``code`` with ``bricklayer`` plus ``scope`` available, capturing stdout."""
    import bricklayer

    namespace = {"bricklayer": bricklayer, **scope}
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            exec(compile(code, "<explore>", "exec"), namespace)
    except Exception:
        printed = build_execution.cap_output(buf.getvalue())
        if printed and not printed.endswith("\n"):
            printed += "\n"
        return SnippetResult(
            ok=False, output=f"{printed}explore error:\n{traceback.format_exc()}"
        )

    out = build_execution.cap_output(buf.getvalue())
    return SnippetResult(ok=True, output=out or "(explore produced no output)")
