"""Tests for the TestContext check harness and the validation report models."""

from bricklayer import Color, LegoBuild, Position, brick

from brickwright.tools.testing import CheckResult, TestContext


def grounded():
    m = LegoBuild()
    m.add(brick(2, 2, color=Color.RED), Position(0, 0, 0))
    return m


def floating():
    m = LegoBuild()
    m.add(brick(1, 1, color=Color.BLUE), Position(10, 0, 0))
    m.add(brick(2, 2, color=Color.RED), Position(0, 0, 3))  # hovering
    return m


def colliding():
    m = LegoBuild()
    m.add(brick(2, 2, color=Color.RED), Position(0, 0, 0))
    m.add(brick(2, 2, color=Color.BLUE), Position(0, 0, 0))
    return m


def two_islands():
    m = LegoBuild()
    m.add(brick(2, 2, color=Color.RED), Position(0, 0, 0))
    m.add(brick(2, 2, color=Color.BLUE), Position(10, 10, 0))  # far apart, unjoined
    return m


class TestCustomCheck:
    def test_records_a_passing_check(self):
        ctx = TestContext(grounded())
        result = ctx.check("over 1 brick", True)
        assert result == CheckResult(name="over 1 brick", passed=True, detail=None)
        assert ctx.report() == [result]

    def test_records_a_failing_check_with_a_detail(self):
        ctx = TestContext(grounded())
        result = ctx.check("over 100 bricks", False, "only 1 brick")
        assert result.passed is False
        assert result.detail == "only 1 brick"

    def test_a_passing_check_drops_its_detail(self):
        ctx = TestContext(grounded())
        assert ctx.check("fine", True, "ignored").detail is None


class TestBuiltinChecks:
    def test_no_floating_passes_for_a_grounded_model(self):
        ctx = TestContext(grounded())
        result = ctx.check_no_floating()
        assert isinstance(result, CheckResult)
        assert result.name == "no_floating"
        assert result.passed is True
        assert result.detail is None
        assert ctx.report() == [result]

    def test_no_floating_fails_and_describes_floaters(self):
        ctx = TestContext(floating())
        result = ctx.check_no_floating()
        assert result.passed is False
        assert result.detail  # names the floating part(s)

    def test_an_unnamed_part_is_described_by_its_part_name(self):
        detail = TestContext(floating()).check_no_floating().detail
        assert detail is not None
        assert brick(2, 2).spec.name in detail
        assert "Element" not in detail

    def test_a_named_part_is_described_by_its_name(self):
        m = LegoBuild()
        m.add(brick(1, 1), Position(10, 0, 0))
        m.add(brick(2, 2, color=Color.RED), Position(0, 0, 3), name="roof")
        detail = TestContext(m).check_no_floating().detail
        assert detail is not None
        assert "roof @" in detail

    def test_description_uses_the_placement_origin(self):
        m = LegoBuild()
        m.add(brick(1, 1), Position(10, 0, 0))
        placed = m.add(brick(2, 2), (0, 0, 3), name="roof")
        assert placed.pose.translation != placed.alignment_box[0]
        detail = TestContext(m).check_no_floating().detail
        assert detail == f"1 floating: roof @ {placed.pose.translation}"

    def test_no_collisions_passes_when_clear(self):
        ctx = TestContext(grounded())
        assert ctx.check_no_collisions().passed is True

    def test_no_collisions_fails_and_describes_the_overlap(self):
        ctx = TestContext(colliding())
        result = ctx.check_no_collisions()
        assert result.passed is False
        assert result.detail is not None
        assert "overlaps" in result.detail


class TestConnected:
    def test_passes_for_a_single_component(self):
        result = TestContext(grounded()).check_connected()
        assert result.name == "connected"
        assert result.passed is True
        assert result.detail is None

    def test_fails_and_reports_the_component_count(self):
        result = TestContext(two_islands()).check_connected()
        assert result.passed is False
        assert result.detail is not None
        assert "Expected 1" in result.detail and "found 2" in result.detail

    def test_honors_an_expected_component_count(self):
        assert TestContext(two_islands()).check_connected(expected_components=2).passed


class TestReport:
    def test_report_returns_check_results_in_call_order(self):
        ctx = TestContext(grounded())
        ctx.check_no_floating()
        ctx.check_no_collisions()
        ctx.check("custom", True)
        report = ctx.report()
        assert all(isinstance(c, CheckResult) for c in report)
        assert [c.name for c in report] == ["no_floating", "no_collisions", "custom"]


class TestMotion:
    def test_motion_check_is_optional(self):
        ctx = TestContext(floating())
        assert ctx.report() == []
        result = ctx.check_motion()
        assert result.name == "motion"
        assert not result.passed
        assert result.detail is not None
        assert "floating" in result.detail
        assert ctx.report() == [result]

    def test_clear_range_passes_and_preserves_model(self):
        from bricklayer import Element, MotionRange, Revolute

        model = LegoBuild()
        base = model.add(Element("3680", Color.WHITE))
        model.connect(
            Element("3679", Color.RED),
            "turntable_pin",
            to=base.find_connector("turntable_socket"),
            motion=MotionRange(Revolute(-45), Revolute(45)),
        )
        original = model.placements
        result = TestContext(model).check_motion(samples=3)
        assert result.passed
        assert model.placements == original

    def test_invalid_sample_budget_is_not_a_pass(self):
        import pytest

        with pytest.raises(ValueError, match="samples"):
            TestContext(grounded()).check_motion(samples=1)
