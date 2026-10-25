import pytest

from brickwright.driver.report import RunReport
from brickwright.tools.validation import ValidationReport


@pytest.mark.parametrize(
    "source,validated,done,ok,expected",
    [
        ("final", "final", True, True, True),
        ("final", "earlier", True, True, False),
        (None, None, True, True, False),
        ("final", "final", False, True, False),
        ("final", "final", True, False, False),
    ],
)
def test_success_requires_validation_of_the_final_exported_source(
    source, validated, done, ok, expected
):
    report = RunReport(
        source_sha256=source,
        done=done,
        turns=1,
        validations=1,
        report=ValidationReport(source_sha256=validated, ok=ok),
    )
    assert report.succeeded is expected
