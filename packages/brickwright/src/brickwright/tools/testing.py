"""The check harness a record's ``run_tests()`` uses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from bricklayer import Element, LegoBuild, Placement

# Cap how many collision/floating items we echo back, to keep details compact.
_MAX_SAMPLE = 20


class CheckResult(BaseModel):
    """The outcome of a single check: did it pass, and why not if it failed."""

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    detail: str | None = None


class TestContext:
    """Accumulates :class:`CheckResult` outcomes for a single build."""

    __test__ = False  # prevent pytest from collecting this class

    def __init__(self, build: LegoBuild) -> None:
        self.build = build
        self._results: list[CheckResult] = []

    def check(self, name: str, ok: bool, detail: str | None = None) -> CheckResult:
        """Record a check; ``detail`` explains a failure (dropped when it passes)."""
        passed = bool(ok)
        result = CheckResult(
            name=name, passed=passed, detail=None if passed else detail
        )
        self._results.append(result)
        return result

    def check_no_floating(self) -> CheckResult:
        """Pass when nothing floats -- every part is supported down to the ground."""
        floaters = self.build.floating_placements
        detail = None
        if floaters:
            sample = "; ".join(
                _describe_placement(self.build, p) for p in floaters[:_MAX_SAMPLE]
            )
            detail = f"{len(floaters)} floating: {sample}"
        return self.check("no_floating", not floaters, detail)

    def check_no_collisions(self) -> CheckResult:
        """Pass when no two parts collide."""
        pairs = self.build.colliding_placements
        detail = None
        if pairs:
            sample = "; ".join(
                f"{_describe_placement(self.build, a)}  overlaps  "
                f"{_describe_placement(self.build, b)}"
                for a, b in pairs[:_MAX_SAMPLE]
            )
            detail = f"{len(pairs)} collisions: {sample}"
        return self.check("no_collisions", not pairs, detail)

    def check_connected(self, expected_components: int = 1) -> CheckResult:
        """Pass when the parts form exactly ``expected_components`` components.

        Compatible mated connectors join parts; merely touching faces do not.
        The default
        expects a single component; a legitimately multipart build -- say a
        scene with two separate buildings -- passes its expected count. This
        says nothing about the ground: a hovering but internally joined stack
        is connected.
        """
        n_components = self.build.num_connected_components
        is_connected = n_components == expected_components
        detail = None
        if not is_connected:
            detail = (
                f"Expected {expected_components} connected component(s), "
                f"found {n_components}"
            )
        return self.check("connected", is_connected, detail)

    def check_motion(
        self, *, samples: int = 5, max_samples: int = 10000
    ) -> CheckResult:
        """Optionally check annotated motion for collisions, floating, and disengagement.

        Samples every combination of the declared ranges, including rest and limits.
        Unannotated connections remain rigid, so the check can flag motions that
        would be possible with additional flexibility. A pass covers only the
        samples. Invalid ranges, motion loops, or an exceeded sample budget raise.
        """
        report = self.build.check_motion(samples=samples, max_samples=max_samples)
        problems = []
        for failure in report.collisions[:_MAX_SAMPLE]:
            a, b = failure.placements
            problems.append(
                f"collision: {_describe_placement(self.build, a)} overlaps "
                f"{_describe_placement(self.build, b)} at "
                f"{[coordinates for _, coordinates in failure.positions]}"
            )
        for failure in report.floating[:_MAX_SAMPLE]:
            parts = "; ".join(
                _describe_placement(self.build, p)
                for p in failure.placements[:_MAX_SAMPLE]
            )
            problems.append(
                f"floating: {parts} at "
                f"{[coordinates for _, coordinates in failure.positions]}"
            )
        if report.disconnections:
            problems.append(f"{len(report.disconnections)} connector disengagements")
        detail = f"{report.samples_checked} samples checked; " + "; ".join(problems)
        return self.check("motion", report.passed, detail)

    def report(self) -> list[CheckResult]:
        """The check results in the order they were run."""
        return list(self._results)


def _describe_placement(build: LegoBuild, placement: Placement[Element]) -> str:
    label = build.name_of(placement) or placement.content.spec.name
    return f"{label} @ {placement.pose.translation}"
