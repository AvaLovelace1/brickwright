from bricklayer import (
    PLATE,
    Color,
    Element,
    LegoBuild,
    Position,
    Rotation,
    brick,
    plate,
)

from brickwright import TestContext

# Coordinate plan:
#   x = beam (across the ship), 0..7  (8 studs wide)
#   y = length (stern y=0  ->  bow y=high)
#   z = height in bricks


def hull_rows():
    """Return {y: (x0, x1)} footprint for each length row, tapering at the bow."""
    rows = {}
    for y in range(30):
        if y <= 23:
            rows[y] = (0, 8)
        elif y == 24 or y == 25:
            rows[y] = (1, 7)
        elif y == 26 or y == 27:
            rows[y] = (2, 6)
        elif y == 28:
            rows[y] = (3, 5)
        else:
            rows[y] = (3, 5)
    return rows


def fill_layer(model, z, rows, color, prefix):
    """Fill a footprint at height z with 2x1 bricks (+ 1x1 to finish odd widths)."""
    n = 0
    for y, (x0, x1) in rows.items():
        x = x0
        while x < x1:
            if x + 2 <= x1:
                model.add(
                    brick(2, 1, color=color),
                    Position(x, y, z),
                    name=f"{prefix}_{x}_{y}",
                )
                x += 2
            else:
                model.add(
                    brick(1, 1, color=color),
                    Position(x, y, z),
                    name=f"{prefix}_{x}_{y}",
                )
                x += 1
            n += 1
    return n


def create_build():
    model = LegoBuild()
    rows = hull_rows()

    # --- Hull: three brick courses ---
    fill_layer(model, 0, rows, Color.DARK_BLUE, "hull0")
    fill_layer(model, 1, rows, Color.DARK_BLUE, "hull1")
    fill_layer(model, 2, rows, Color.RED, "hull2")  # red boot-stripe / waterline band

    # --- Main deck: big plates that bridge the whole hull into one assembly ---
    deck_color = Color.WHITE
    model.add(plate(8, 8, color=deck_color), Position(0, 0, 3), name="deck0")
    model.add(plate(8, 8, color=deck_color), Position(0, 8, 3), name="deck1")
    model.add(plate(8, 8, color=deck_color), Position(0, 16, 3), name="deck2")
    model.add(plate(6, 6, color=deck_color), Position(1, 24, 3), name="deck3")

    # Bridge the deck plates into one assembly with overlapping plates on top.
    model.add(
        plate(16, 8, color=deck_color),
        Position(0, 4, 3 + PLATE),
        Rotation.DEG_90,
        name="deckbridge0",
    )
    model.add(
        plate(8, 6, color=deck_color),
        Position(1, 20, 3 + PLATE),
        Rotation.DEG_90,
        name="deckbridge1",
    )

    # Deck top surface elevation (two plates above the z=3 brick course top).
    deck_top = 3 + 2 * PLATE

    build_superstructure(model, deck_top)

    return model


def fill_block(model, z, x0, x1, y0, y1, color, prefix):
    """Fill a rectangle [x0,x1) x [y0,y1) at height z with 2x1 bricks."""
    for y in range(y0, y1):
        x = x0
        while x < x1:
            if x + 2 <= x1:
                model.add(
                    brick(2, 1, color=color),
                    Position(x, y, z),
                    name=f"{prefix}_{x}_{y}",
                )
                x += 2
            else:
                model.add(
                    brick(1, 1, color=color),
                    Position(x, y, z),
                    name=f"{prefix}_{x}_{y}",
                )
                x += 1


def build_superstructure(model, z0):
    glass = Color.TRANS_LIGHT_BLUE
    white = Color.WHITE

    # --- Tier 1 deck house: white / window-band / white ---
    fill_block(model, z0, 1, 7, 5, 24, white, "t1a")
    fill_block(model, z0 + 1, 1, 7, 5, 24, glass, "t1win")
    fill_block(model, z0 + 2, 1, 7, 5, 24, white, "t1b")
    # floor plate bridging tier 1 top
    model.add(
        plate(16, 6, color=white),
        Position(1, 5, z0 + 3),
        Rotation.DEG_90,
        name="t1deck0",
    )
    model.add(plate(6, 2, color=white), Position(1, 21, z0 + 3), name="t1deck1")
    model.add(plate(6, 1, color=white), Position(1, 23, z0 + 3), name="t1deck2")

    # --- Tier 2 deck house (narrower): white / window-band / white ---
    z1 = z0 + 3 + PLATE
    fill_block(model, z1, 2, 6, 8, 21, white, "t2a")
    fill_block(model, z1 + 1, 2, 6, 8, 21, glass, "t2win")
    fill_block(model, z1 + 2, 2, 6, 8, 21, white, "t2b")
    for i, dy in enumerate((8, 12, 16)):
        model.add(plate(4, 4, color=white), Position(2, dy, z1 + 3), name=f"t2deck{i}")
    model.add(plate(4, 1, color=white), Position(2, 20, z1 + 3), name="t2deck3")

    # --- Bridge / wheelhouse near the bow (front, high y) ---
    z2 = z1 + 3 + PLATE
    fill_block(model, z2, 2, 6, 17, 20, white, "bridgea")
    fill_block(model, z2 + 1, 2, 6, 17, 20, Color.DARK_AZURE, "bridgewin")
    model.add(plate(4, 2, color=white), Position(2, 17, z2 + 2), name="bridgeroof0")
    model.add(plate(4, 1, color=white), Position(2, 19, z2 + 2), name="bridgeroof1")

    # --- Radar mast atop the bridge ---
    model.add(
        brick(1, 1, 3, color=Color.LIGHT_BLUISH_GRAY),
        Position(3, 18, z2 + 2 + PLATE),
        name="mast",
    )
    model.add(
        Element("4032a", Color.WHITE),
        Position(3, 18, z2 + 2 + PLATE + 3),
        name="radar",
    )

    # --- Funnels on the sun deck (rear) ---
    funnel_color = Color.RED
    for i, fy in enumerate((10, 14)):
        model.add(
            Element("3941", funnel_color), Position(3, fy, z2), name=f"funnel{i}a"
        )
        model.add(
            Element("3941", funnel_color),
            Position(3, fy, z2 + 1),
            name=f"funnel{i}b",
        )
        model.add(
            Element("3941", Color.DARK_BLUE),
            Position(3, fy, z2 + 2),
            name=f"funnelband{i}",
        )
        model.add(
            Element("14769", Color.BLACK),
            Position(3, fy, z2 + 3),
            name=f"funnelcap{i}",
        )

    # --- Railings around the tier-1 sun deck edges (rear, y 5..9) ---
    rail = Color.WHITE
    rz = z0 + 3 + PLATE
    model.add(Element("3185", rail), Position(1, 5, rz), name="rail_rear")
    model.add(
        Element("3185", rail),
        Position(1, 6, rz),
        Rotation.DEG_90,
        name="rail_left",
    )
    model.add(
        Element("3185", rail),
        Position(6, 6, rz),
        Rotation.DEG_90,
        name="rail_right",
    )

    # --- Lifeboats hung along tier-1 deck (orange) ---
    for i, ly in enumerate((6, 10, 14, 18)):
        model.add(
            brick(2, 1, color=Color.ORANGE),
            Position(0, ly, z0),
            Rotation.DEG_90,
            name=f"boatL{i}",
        )
        model.add(
            brick(2, 1, color=Color.ORANGE),
            Position(7, ly, z0),
            Rotation.DEG_90,
            name=f"boatR{i}",
        )


def run_tests():
    model = create_build()
    tests = TestContext(model)
    tests.check_no_floating()
    tests.check_no_collisions()
    tests.check_connected(expected_components=1)
    tests.check(
        "over 100 bricks", model.brick_count > 100, f"brick_count={model.brick_count}"
    )
    return tests.report()
