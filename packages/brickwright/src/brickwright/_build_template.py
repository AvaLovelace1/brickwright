import bricklayer as bl

from brickwright import TestContext


def create_build():
    """Return the finished :class:`bricklayer.LegoBuild`."""
    build = bl.LegoBuild()
    # TODO: assemble the requested build
    build.add(
        bl.brick(2, 2, color=bl.Color.RED), bl.Position(0, 0, 0), bl.Rotation.FRONT
    )
    return build


def run_tests():
    """Create the build and return a report of which checks passed."""
    build = create_build()
    tests = TestContext(build)
    tests.check_no_floating()
    tests.check_no_collisions()
    tests.check_connected(expected_components=1)
    # Add a custom check for any measurable requirement, e.g.:
    # tests.check("over 100 bricks", build.brick_count > 100)
    return tests.report()
