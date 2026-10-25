"""Agent-facing tools, loaded on first access so importing one skips the rest."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .editing import edit_build, insert_build, multi_edit_build
    from .exploration import SnippetResult, explore
    from .finalization import FinalizationReport, finalize
    from .registry import ToolOutcome, available_tools, execute_tool
    from .rendering import (
        RenderReport,
        angle_to_view_dir,
        render,
        render_angle,
        render_available,
        render_views,
    )
    from .testing import CheckResult, TestContext
    from .validation import ValidationReport, validate

_SUBMODULES = {
    "editing": ("edit_build", "insert_build", "multi_edit_build"),
    "exploration": ("SnippetResult", "explore"),
    "finalization": ("FinalizationReport", "finalize"),
    "registry": ("ToolOutcome", "available_tools", "execute_tool"),
    "rendering": (
        "RenderReport",
        "angle_to_view_dir",
        "render",
        "render_angle",
        "render_available",
        "render_views",
    ),
    "testing": ("CheckResult", "TestContext"),
    "validation": ("ValidationReport", "validate"),
}
_SOURCE = {name: module for module, names in _SUBMODULES.items() for name in names}

__all__ = [
    "CheckResult",
    "FinalizationReport",
    "RenderReport",
    "SnippetResult",
    "TestContext",
    "ToolOutcome",
    "ValidationReport",
    "angle_to_view_dir",
    "available_tools",
    "edit_build",
    "execute_tool",
    "explore",
    "finalize",
    "insert_build",
    "multi_edit_build",
    "render",
    "render_angle",
    "render_available",
    "render_views",
    "validate",
]


def __getattr__(name: str) -> Any:
    if name not in _SOURCE:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{_SOURCE[name]}", __name__), name)
    globals()[name] = value
    return value
