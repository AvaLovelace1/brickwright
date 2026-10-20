from fractions import Fraction
from bricklayer import Color, Element, LegoBuild, Rotation

DOOR_X = 4
P = Fraction(1, 3)


def create_build():
    b = LegoBuild()
    b.add(Element("41539", Color.GREEN), name="garden")
    b.add(Element("3032", Color.LIGHT_BLUISH_GRAY), (1, 2, P))
    z = 2 * P
    roof_z = z + 2

    # Walls and door
    for x in range(1, 7):
        if x not in (DOOR_X, DOOR_X + 1):
            b.add(Element("14716", Color.RED), (x, 2, z))
    b.add(Element("22886", Color.REDDISH_BROWN), (DOOR_X, 2, z))
    for x in (1, 6):
        b.add(Element("22886", Color.RED), (x, 3, z), Rotation.LEFT)
    for level in range(3):
        b.add(Element("3009", Color.RED), (1, 5, z + level))
    b.add(Element("3032", Color.WHITE), (1, 2, roof_z), name="eaves")

    # Six-part roof
    roof = LegoBuild()
    roof.add(Element("3032", Color.BLUE))
    for x in (0, 3):
        roof.add(Element("3038", Color.BLUE), (x, 0, P))
        roof.add(Element("3038", Color.BLUE), (x, 2, P), Rotation.BACK)
    roof.add(Element("3795", Color.BLUE), (0, 1, P + 1))
    b.add(roof, (1, 2, roof_z + P), name="roof")
    b.add(Element("3068b", Color.LIGHT_BLUISH_GRAY), (DOOR_X, 0, P))
    return b


def run_tests():
    b = create_build()
    assert not b.colliding_placements()
    assert not b.floating_placements()
    assert len(b.connected_components()) == 1
    assert b.brick_count == 20
