"""BrickWright record 20260630-181551-create-this-object-in-664a4bfe."""

from bricklayer import Color, LegoBuild, Position, Rotation, brick

from brickwright import TestContext


# The photo shows a studded, block-built watermelon slice: a stepped red
# triangle two studs thick, a bright lime rind stripe, a darker green rind, and
# five black 1x1 seed bricks embedded only in the front face.
RED_ROWS = {
    9: (6, 8),    # top 2-stud cap
    8: (5, 9),    # 4 wide
    7: (4, 10),   # 6 wide
    6: (3, 11),   # 8 wide
    5: (2, 12),   # 10 wide
    4: (1, 13),   # 12 wide
    3: (0, 14),   # broad bottom of the flesh
}
RIND_ROWS = {
    2: (0, 14, Color.LIME),
    1: (2, 12, Color.GREEN),
    0: (4, 10, Color.GREEN),
}
SEEDS = {
    (2, 4),
    (5, 3),
    (6, 6),
    (8, 5),
    (11, 4),
}


def _split_width(width, *, depth):
    """Return real brick widths that add up to width for the given depth."""
    if depth == 2:
        allowed = (10, 8, 6, 4, 3, 2)
    else:
        allowed = (10, 8, 6, 4, 3, 2, 1)
    pieces = []
    remaining = width
    for candidate in allowed:
        while remaining >= candidate:
            # Avoid leaving an impossible 1-stud remainder for 2-deep bricks.
            if depth == 2 and remaining - candidate == 1:
                break
            pieces.append(candidate)
            remaining -= candidate
    if remaining:
        if depth == 2:
            # The row sizes used in this model are all even/valid, so this is a
            # defensive guard rather than normal flow.
            raise ValueError(f"cannot split {width} studs into 2-deep bricks")
        pieces.extend([1] * remaining)
    return pieces


def _add_run(model, *, x0, x1, y, z, depth, color, prefix):
    """Fill a horizontal run [x0, x1) with legal LEGO brick elements."""
    x = x0
    for i, width in enumerate(_split_width(x1 - x0, depth=depth)):
        model.add(
            brick(width, depth, color=color),
            Position(x, y, z),
            Rotation.FRONT,
            name=f"{prefix}_{i}_x{x}_z{z}_d{depth}",
        )
        x += width


def _add_solid_two_deep_row(model, *, z, x0, x1, color, prefix):
    """Add a normal two-stud-deep brick course."""
    _add_run(
        model,
        x0=x0,
        x1=x1,
        y=0,
        z=z,
        depth=2,
        color=color,
        prefix=prefix,
    )


def _add_red_row_with_front_seeds(model, *, z, x0, x1):
    """Add one red flesh course, replacing the visible face with black seeds."""
    seed_xs = sorted(x for x, seed_z in SEEDS if seed_z == z and x0 <= x < x1)

    # The renderer's front view looks at the max-y face, so the visible face is
    # y=1.  Red brick runs are interrupted by black 1x1 seed bricks there.
    start = x0
    seed_index = 0
    for sx in seed_xs:
        if start < sx:
            _add_run(
                model,
                x0=start,
                x1=sx,
                y=1,
                z=z,
                depth=1,
                color=Color.RED,
                prefix=f"red_front_z{z}_run{seed_index}",
            )
        model.add(
            brick(1, 1, color=Color.BLACK),
            Position(sx, 1, z),
            Rotation.FRONT,
            name=f"black_seed_x{sx}_z{z}",
        )
        start = sx + 1
        seed_index += 1
    if start < x1:
        _add_run(
            model,
            x0=start,
            x1=x1,
            y=1,
            z=z,
            depth=1,
            color=Color.RED,
            prefix=f"red_front_z{z}_run{seed_index}",
        )

    # The rear half of the same course stays red, keeping the slice two studs
    # thick without duplicating the black seeds all the way through.
    _add_run(
        model,
        x0=x0,
        x1=x1,
        y=0,
        z=z,
        depth=1,
        color=Color.RED,
        prefix=f"red_back_z{z}",
    )


def create_build():
    """Return the finished :class:`bricklayer.LegoBuild`."""
    model = LegoBuild()

    # Dark-green rounded outer rind and bright lime inner stripe.
    for z, (x0, x1, color) in RIND_ROWS.items():
        _add_solid_two_deep_row(
            model,
            z=z,
            x0=x0,
            x1=x1,
            color=color,
            prefix=f"rind_z{z}",
        )

    # Stepped triangular red flesh, with black seed bricks embedded in the
    # visible face wherever the reference model shows them.
    for z in sorted(RED_ROWS):
        x0, x1 = RED_ROWS[z]
        if any(seed_z == z for _, seed_z in SEEDS):
            _add_red_row_with_front_seeds(model, z=z, x0=x0, x1=x1)
        else:
            _add_solid_two_deep_row(
                model,
                z=z,
                x0=x0,
                x1=x1,
                color=Color.RED,
                prefix=f"red_solid_z{z}",
            )

    return model


def run_tests():
    """Build the model and return a report of which checks passed."""
    model = create_build()
    tests = TestContext(model)
    tests.check_no_floating()
    tests.check_no_collisions()
    tests.check_connected(expected_components=1)

    flat = model.flatten()
    colors = [p.content.color for p in flat]
    tests.check("watermelon is two studs thick", model.depth == 2, f"depth={model.depth}")
    tests.check("stepped triangular slice silhouette", model.width == 14 and model.height == 10, f"box={model.bounding_box}")
    tests.check("five black seeds", colors.count(Color.BLACK) == 5, f"black parts={colors.count(Color.BLACK)}")
    tests.check("red flesh dominates upper slice", colors.count(Color.RED) >= 19, f"red parts={colors.count(Color.RED)}")
    tests.check("lime stripe and green rind present", Color.LIME in colors and Color.GREEN in colors)
    for sx, sz in SEEDS:
        tests.check(
            f"seed at x={sx}, z={sz}",
            f"black_seed_x{sx}_z{sz}" in model.names,
        )
    return tests.report()
