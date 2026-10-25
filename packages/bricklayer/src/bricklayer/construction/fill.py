"""Construction helpers.

Fill simple boxes or wedges with valid parts. Large hollow structures should
be built from separate walls rather than filling their entire interior.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator

from ..colors import Color
from ..geometry import (
    PLATE,
    Direction,
    HeightLike,
    Pose,
    Position,
    Rotation,
    to_bricks,
    to_plates,
)
from ..geometry.linalg import Scalar, vec_max, vec_min
from ..geometry.spatial import (
    BUILD_TOLERANCE,
    PLATES_PER_BRICK,
    require_grid_position,
    to_whole_studs,
)
from ..modeling.build import LegoBuild
from ..modeling.transforms import flatten, translate
from ..parts.element import Element
from ..parts.shape import Box, Footprint
from ._factories import PartOptions
from .angled import _INVERTED_SLOPES, _SLOPES, inverted_slope, slope
from .basic import _BRICKS, _PLATES

_HORIZONTAL = (Direction.FRONT, Direction.BACK, Direction.RIGHT, Direction.LEFT)

# Each wedge kind's options and factory, keyed by ``inverted``.
_WEDGE_PARTS: dict[bool, tuple[PartOptions, Callable[..., Element]]] = {
    False: (_SLOPES, slope),
    True: (_INVERTED_SLOPES, inverted_slope),
}

# Rotation that points an (unrotated, downhill = -Y) slope's descent at `toward`.
_DESCENT_ROTATION = {
    Direction.FRONT: Rotation.DEG_0,
    Direction.LEFT: Rotation.DEG_90,
    Direction.BACK: Rotation.DEG_180,
    Direction.RIGHT: Rotation.DEG_270,
}


def _part_widths(
    options: PartOptions,
    *,
    depth: int = 1,
    height: HeightLike = 1,
) -> tuple[int, ...]:
    """Widths of parts in the given options that have the given depth and height, sorted descending.

    Rotated parts are included, so a 1x2 brick will be counted for depth=1 and depth=2. ``height`` is ignored for plates.
    """
    widths: set[int] = set()
    for part in options.specs:
        assert isinstance(part.shape, (Box, Footprint))
        for shape in part.shape, part.shape.transpose():
            if isinstance(shape, Box):
                if shape.depth == depth and shape.height == height:
                    widths.add(shape.width)
            elif isinstance(shape, Footprint) and shape.depth == depth:
                widths.add(shape.width)
    return tuple(sorted(widths, reverse=True))


def _box_corners(
    corner_a: Position | tuple[float, float, float],
    corner_b: Position | tuple[float, float, float],
) -> tuple[Position, int, int, Scalar]:
    """Normalize two grid corners into ``(min corner, width, depth, height)``.

    The corners may be given in any order. Raises ValueError if either corner
    is off the integer build grid.
    """
    corners = [require_grid_position(corner_a), require_grid_position(corner_b)]
    lo, hi = vec_min(corners), vec_max(corners)
    plates = to_plates(hi.z) - to_plates(lo.z)
    whole_bricks, remainder = divmod(plates, PLATES_PER_BRICK)
    height: Scalar = whole_bricks if remainder == 0 else to_bricks(plates)
    return lo, to_whole_studs(hi.x - lo.x), to_whole_studs(hi.y - lo.y), height


def fill_box(
    corner_a: Position | tuple[float, float, float],
    corner_b: Position | tuple[float, float, float],
    color: Color = Color.WHITE,
) -> LegoBuild:
    """Return a model filling the box between two grid corners, in either order.

    Uses bricks and plates without collisions; connected if taller than ``PLATE``.
    Uses a single part when a brick or plate fits, including rotated sizes.
    The interior is solid: use separate wall calls for large hollow structures,
    and smaller calls for color patterns or details.

    Raises ``ValueError`` for off-grid corners or zero extent on any axis.
    """
    lo, width, depth, height = _box_corners(corner_a, corner_b)
    return translate(_fill_box(width, depth, height, color), lo)


def _require_positive_box(width: int, depth: int, height: Scalar) -> None:
    """Raise unless every box dimension is positive."""
    if width <= 0 or depth <= 0 or height <= 0:
        raise ValueError(f"dimensions must be positive, got {width}x{depth}x{height}")


def _fill_box(width: int, depth: int, height: Scalar, color: Color) -> LegoBuild:
    """Fill a ``width x depth x height`` box with its min corner at the origin."""
    _require_positive_box(width, depth, height)
    found = _single_part(width, depth, height, color)
    if found is not None:
        return _one(*found)

    if width >= depth:
        return _fill_box_courses(width, depth, height, color)
    else:
        # Swap dims to make brick widths align with the wider box dimension.
        m = LegoBuild()
        m.extend(_fill_box(depth, width, height, color), rotation=Rotation.DEG_90)
        return m


def _fill_box_courses(
    width: int, depth: int, height: Scalar, color: Color
) -> LegoBuild:
    """Greedily fill a box with the given dimensions.

    The box is filled course by course (see :func:`_fill_course`), alternating
    between two course patterns. Seams on even (odd)-numbered courses are at even (odd) positions,
    guaranteeing that no two seams coincide and the resulting model is connected.
    """
    offset_y = 1 if depth > 2 else 0

    # Precompute the four distinct course patterns (staggered or not, brick or
    # plate), threading the x-offset through them so staggered courses differ.
    courses: dict[tuple[bool, bool], LegoBuild] = {}
    offset_x = 0
    for use_offsets in (False, True):
        for use_plates in (False, True):
            course = _fill_course(
                width,
                depth,
                offset_x=use_offsets * offset_x,
                offset_y=use_offsets * offset_y,
                color=color,
                use_plates=use_plates,
            )
            courses[(use_offsets, use_plates)] = course
            offset_x = _stagger_x(course, offset_x)

    m = LegoBuild()
    for i, z, use_plates in _courses(height):
        m.extend(courses[(bool(i % 2), use_plates)], Position(0, 0, z))
    return m


def _fill_course(
    width: int,
    depth: int,
    *,
    offset_x: int = 0,
    offset_y: int = 0,
    color: Color = Color.WHITE,
    use_plates: bool = False,
) -> LegoBuild:
    """Greedily fill a single course (layer) of bricks or plates with a regular pattern.

    The course is tiled using rows of depth-2 bricks/plates, with a depth-1 row at the
    end if depth is odd. Each row is greedy-filled with the widest available parts.
    The parts are always of even width, unless ``width`` is odd, in which case a width-3 part
    (or width-1 part in the case of a width-1 row) is used to fill the last studs of the row.
    When ``offset=0``, this means that seams are always at even x-positions.

    ``offset_x``, ``offset_y`` force a seam to be at ``x=offset_x`` and ``y=offset_y``,
    which is useful for staggering seams between courses.
    """
    if width == 0 or depth == 0:
        return LegoBuild()
    if width < 0 or depth < 0:
        raise ValueError(f"dimensions must be non-negative, got {width}x{depth}")
    if offset_x < 0 or offset_y < 0:
        raise ValueError(f"offsets must be non-negative, got {offset_x}, {offset_y}")
    if offset_x > width or offset_y > depth:
        raise ValueError(
            f"offsets must be <= dimensions, got {offset_x}, {offset_y} for {width}x{depth}"
        )

    # Recursively fill the course in quadrants if offsets are specified.
    if offset_x or offset_y:
        m = LegoBuild()
        for y, d in ((0, offset_y), (offset_y, depth - offset_y)):
            for x, w in ((0, offset_x), (offset_x, width - offset_x)):
                quadrant = _fill_course(w, d, color=color, use_plates=use_plates)
                m.extend(quadrant, Position(x, y, 0))
        return m

    # For odd widths, break it down into a 1-deep or 3-deep section and a remainder that is even.
    if width > 3 and width % 2 != 0:
        body = _fill_course(width - 3, depth, color=color, use_plates=use_plates)
        tail = _fill_course(3, depth, color=color, use_plates=use_plates)
        m = LegoBuild()
        m.extend(body, Position.ZERO)
        m.extend(tail, Position(width - 3, 0, 0))
        return m

    m = LegoBuild()
    options = _PLATES if use_plates else _BRICKS
    height = PLATE if use_plates else 1

    def get_allowed_widths(d: int) -> tuple[int, ...]:
        if width == 1:
            return (1,)
        elif width == 3:
            return (3,)
        else:  # width is even, so only even-width parts are needed
            return tuple(w for w in _part_widths(options, depth=d) if w % 2 == 0)

    allowed_widths = {d: get_allowed_widths(d) for d in [1, 2]}
    rows = {d: _greedy_fill_row(width, allowed_widths[d]) for d in [1, 2]}

    parts: dict[tuple[int, int], tuple[Element, Rotation]] = {}
    # Tile the course with 2-deep rows, with a 1-deep row at the end if depth is odd.
    for y in range(0, depth, 2):
        row_depth = 1 if y == depth - 1 and depth % 2 else 2
        x = 0
        for part_width in rows[row_depth]:
            key = (part_width, row_depth)
            if key not in parts:
                found = _single_part(part_width, row_depth, height, color)
                assert found is not None
                parts[key] = found
            element, rotation = parts[key]
            m.add(element, Position(x, y, 0), rotation=rotation)
            x += part_width
    return m


def _greedy_fill_row(width: int, allowed_widths: tuple[int, ...]) -> list[int]:
    """Greedily fill a row of the given width with the allowed part widths.

    Goes down the list of allowed widths, taking the first that fits and
    backtracking out of a dead end.

    Raises:
        ValueError: if no combination of ``allowed_widths`` fills ``width``.
    """

    def fill(remaining: int) -> list[int] | None:
        if remaining == 0:
            return []
        for part_width in allowed_widths:
            if part_width > remaining:
                continue
            tail = fill(remaining - part_width)
            if tail is not None:
                return [part_width, *tail]
        return None

    result = fill(width)
    if result is None:
        raise ValueError(
            f"cannot fill row of width {width} with allowed widths {allowed_widths}"
        )
    return result


def _single_part(
    width: int, depth: int, height: Scalar, color: Color
) -> tuple[Element, Rotation] | None:
    """The brick/plate filling the box, and its rotation, if one does."""
    shape: Box | Footprint
    if abs(height - PLATE) <= BUILD_TOLERANCE:
        options, shape = _PLATES, Footprint(width, depth)
    elif isinstance(height, int):
        options, shape = _BRICKS, Box(width, depth, height)
    else:
        return None
    for candidate, rotation in (
        (shape, Rotation.DEG_0),
        (shape.transpose(), Rotation.DEG_90),
    ):
        spec = options.get(candidate)
        if spec is not None:
            return Element(spec.ldraw_id, color), rotation
    return None


def _slope_courses(height: Scalar, slope_height: int) -> int:
    """The number of whole ``slope_height``-brick courses that fit in ``height`` bricks."""
    return to_plates(height, round_down=True) // to_plates(slope_height)


def _courses(height: Scalar) -> Iterator[tuple[int, Scalar, bool]]:
    """Each course stacked to reach ``height``: its index, base z, and whether it
    is plate-high. Brick-high courses come first.

    A height of exactly one brick is built from three plate courses rather than a
    single brick course, so a lone course stays connected to its neighbors.
    """
    if abs(height - 1) <= BUILD_TOLERANCE:
        n_brick, n_plate = 0, 3
    else:
        n_brick, n_plate = divmod(to_plates(height), 3)
    z: Scalar = 0
    for i in range(n_brick + n_plate):
        yield i, z, i >= n_brick
        z += 1 if i < n_brick else PLATE


def _stagger_x(course: LegoBuild, offset_x: int) -> int:
    """The x-seam offset for the course above ``course``.

    Roughly half the widest part in the course (so it looks nice), forced odd so
    successive courses never share a seam. An empty course leaves the offset as-is.
    """
    if not course.placements:
        return offset_x
    half = course.placements[0].content.alignment_width // 2
    return half + 1 if half % 2 == 0 else half


def fill_slope(
    corner_a: Position | tuple[float, float, float],
    corner_b: Position | tuple[float, float, float],
    toward: Direction = Direction.FRONT,
    color: Color = Color.WHITE,
) -> LegoBuild:
    """Fill a sloped wedge inside the axis-aligned box spanned by two corners.

    The corners may be given in any order; the wedge occupies exactly the box
    between them.

    The face of the slope is clad in slope bricks and points in the ``toward`` direction.
    The slope bricks mostly have the same degree, chosen based on the box dimensions,
    with a possible degree change to smooth out the top.
    If the slope bricks cannot cover the wedge exactly, the remaining cuboid volume at the
    back of the slope is filled with regular bricks/plates.

    If the box dims match a single catalog slope (incl. rotation), that one part is returned.

    The resulting model is guaranteed to use valid parts and have no collisions. It is also
    guaranteed to be connected unless there is only one row of slopes.

    Use this function to avoid collisions and connectivity issues when filling a slope shape.
    Since the resulting slope is uniformly colored and featureless, it should be used only for
    simple components and not where complex detail is needed. Alternatively, you can combine
    multiple smaller `fill_slope` calls to create more complex shapes and color patterns.

    Raises:
        ValueError: for off-grid or coinciding corners or a non-horizontal ``toward``.
    """
    lo, width, depth, height = _box_corners(corner_a, corner_b)
    return translate(_fill_wedge(width, depth, height, toward, color), lo)


def fill_inverted_slope(
    corner_a: Position | tuple[float, float, float],
    corner_b: Position | tuple[float, float, float],
    toward: Direction = Direction.FRONT,
    color: Color = Color.WHITE,
) -> LegoBuild:
    """Fill an inverted wedge inside the axis-aligned box spanned by two corners.

    This is the mirror image of :func:`fill_slope` flipped along the z-axis:
    the descending *underside* is clad in inverted slope bricks.
    The face of the slope still points in the ``toward`` direction.
    The corners may be given in any order; the wedge occupies exactly the box
    between them.

    If the box dims match a single catalog inverted slope (incl. rotation), that
    one part is returned.

    The resulting model is guaranteed to use valid parts and have no collisions.
    It is also guaranteed to be connected unless there is only one row of inverted slopes.

    Raises:
        ValueError: for off-grid or coinciding corners or a non-horizontal ``toward``.
    """
    lo, width, depth, height = _box_corners(corner_a, corner_b)
    model = _fill_wedge(width, depth, height, toward, color, inverted=True)
    return translate(model, lo)


def _fill_wedge(
    width: int,
    depth: int,
    height: Scalar,
    toward: Direction,
    color: Color,
    *,
    inverted: bool = False,
) -> LegoBuild:
    """Shared body of :func:`fill_slope` and :func:`fill_inverted_slope`.

    Validates the dimensions, returns a single catalog part when one fits, and
    otherwise builds an unrotated wedge (downhill toward -Y) and rotates it to
    descend in the ``toward`` direction.
    """
    _require_positive_box(width, depth, height)
    if toward not in _HORIZONTAL:
        raise ValueError(f"toward must be a horizontal direction, got {toward}")
    shortcut = _single_slope(width, depth, height, toward, color, inverted)
    if shortcut is not None:
        return shortcut
    model = _fill_slope(
        *_horizontal_run(width, depth, toward), height, color, inverted=inverted
    )
    m = LegoBuild()
    m.extend(model, rotation=_DESCENT_ROTATION[toward])
    return m


def _fill_slope(
    width: int,
    depth: int,
    height: Scalar,
    color: Color,
    dh: tuple[int, int] | None = None,
    *,
    inverted: bool = False,
) -> LegoBuild:
    """Fill a wedge inside the ``width x depth x height`` box, descending toward -Y.

    A regular wedge sits on the ground with its sloped face on top; an ``inverted``
    wedge is its z-mirror, hanging from a full top slab with the sloped face
    underneath. ``dh`` fixes the slope degree (depth, height); when omitted, the
    best-fitting degree for the box is chosen. If no slope fits, the box is filled
    with plain bricks (which are their own z-mirror).
    """
    if width == 0 or depth == 0:
        return LegoBuild()
    options, _ = _WEDGE_PARTS[inverted]
    dh = dh or _best_slope_degree(depth, height, options)
    if dh is None:
        return _fill_box(width, depth, height, color)
    slope_depth, slope_height = dh

    n_slopes = _slope_courses(height, slope_height)
    slope_total_depth = n_slopes * (slope_depth - 1) + 1
    slope_total_height = n_slopes * slope_height

    m = LegoBuild()
    if abs(slope_total_height - height) > BUILD_TOLERANCE:
        # The slopes don't reach the full height, so split the wedge into a
        # full-degree part and a shallower remainder; mirroring swaps which one
        # rests on the ground.
        bottom = _fill_slope(
            width, depth, slope_total_height, color, dh=dh, inverted=inverted
        )
        top = _fill_slope(
            width,
            depth - (slope_total_depth - 1),
            height - slope_total_height,
            color,
            inverted=inverted,
        )
        bottom_z = height - slope_total_height if inverted else 0
        top_z = 0 if inverted else slope_total_height
        m.extend(bottom, Position(0, 0, bottom_z))
        m.extend(top, Position(0, slope_total_depth - 1, top_z))
        return m

    m.extend(
        _fill_slope_face(width, height, slope_depth, slope_height, color, inverted)
    )
    body = _fill_slope_body(width, depth, height, slope_depth, slope_height, color)
    if inverted:
        body = _invert_z(body, height)
    if body.placements:
        # ``extend`` pins the content's min corner to the position, so use the body's
        # own min z (0 for a regular wedge, elevated for an inverted one).
        m.extend(body, Position(0, slope_depth, body.bounding_box[0].z))
    return m


def _fill_slope_face(
    width: int,
    height: Scalar,
    slope_depth: int,
    slope_height: int,
    color: Color,
    inverted: bool = False,
) -> LegoBuild:
    """The sloped face of a wedge, clad in (inverted) slope bricks.

    Courses of slopes are greedy-filled and stacked from the ground up, or from
    the full top slab down when ``inverted``.
    """
    options, make = _WEDGE_PARTS[inverted]
    # Even-width slopes stagger cleanly; a width-1 slope fills the last stud of an
    # odd row (width-3 slopes, unlike bricks, are uncommon).
    allowed_widths = tuple(
        w
        for w in _part_widths(options, depth=slope_depth, height=slope_height)
        if w % 2 == 0 or w == 1
    )
    rows = {
        0: _greedy_fill_row(width, allowed_widths),
        1: [1] + _greedy_fill_row(width - 1, allowed_widths),
    }

    m = LegoBuild()
    for i in range(_slope_courses(height, slope_height)):
        z = height - (i + 1) * slope_height if inverted else i * slope_height
        y = i * (slope_depth - 1)
        x = 0
        for part_width in rows[i % 2]:
            m.add(make(part_width, slope_depth, slope_height, color), Position(x, y, z))
            x += part_width
    return m


def _fill_slope_body(
    width: int,
    depth: int,
    height: Scalar,
    slope_depth: int,
    slope_height: int,
    color: Color,
) -> LegoBuild:
    """The non-sloped portion of a wedge, filled with bricks/plates."""
    offset_x = 0
    offset_y = 1 if depth > 2 else 0
    max_slopes = _slope_courses(height, slope_height)

    m = LegoBuild()
    for i, z, use_plates in _courses(height):
        n_slopes = min(max_slopes, _slope_courses(z, slope_height) + 1)
        y = n_slopes * (slope_depth - 1) + 1  # depth taken up by slopes
        use_offsets = bool(i % 2)
        course = _fill_course(
            width,
            depth - y,
            offset_x=use_offsets * offset_x,
            offset_y=use_offsets * offset_y,
            color=color,
            use_plates=use_plates,
        )
        m.add(course, Position(0, 0, z))
        offset_x = _stagger_x(course, offset_x)

    rotated = LegoBuild()
    rotated.add(flatten(m), rotation=Rotation.DEG_180)
    return flatten(rotated)


def _invert_z(model: LegoBuild, height: Scalar) -> LegoBuild:
    """Reflect ``model`` top-to-bottom within a box of the given ``height`` (bricks).

    Flips z: each part keeps its upright orientation but moves to its mirrored
    height, and slopes are swapped for inverted slopes (and vice versa) so the
    reflected geometry uses valid parts. Reflecting across the full ``height`` rather
    than the model's own extent keeps a subcomponent aligned with the box it lives in.
    """
    model = flatten(model)
    span = to_plates(height) - 1
    m = LegoBuild()
    for p in model.placements:
        top = to_plates(p.alignment_box[1].z) - 1
        t = p.pose.translation
        m.add_raw(
            _flip_slope(p.content),
            Pose(p.pose.rotation, Position(t.x, t.y, to_bricks(span - top))),
        )
    return m


def _flip_slope(content: Element | LegoBuild) -> Element | LegoBuild:
    """Swap a slope element for its inverted counterpart (and vice versa).

    Anything that is not a (regular or inverted) slope is returned unchanged.
    """
    if isinstance(content, Element) and isinstance(content.spec.shape, Box):
        for options, flipped in (
            (_SLOPES, _INVERTED_SLOPES),
            (_INVERTED_SLOPES, _SLOPES),
        ):
            if content.ldraw_id in options.parts:
                return flipped.element(content.spec.shape, content.color)
    return content


def _best_slope_degree(
    depth: int,
    height: Scalar,
    options: PartOptions,
) -> tuple[int, int] | None:
    """Choose the slope degree that best fits in the given box dimensions.

    ``options`` selects which catalog (``SLOPE`` or ``INVERTED_SLOPE``) supplies
    the available degrees. Return None if no slope degree fits.
    """

    def score(slope_depth: int, slope_height: int) -> Scalar:
        """Stack slopes of degree (slope_depth, slope_height) until they reach the given height,
        and return the depth remaining (or math.inf if the stacked slopes exceed ``depth``
        or zero slopes are stacked).
        """
        n_slopes = _slope_courses(height, slope_height)
        if n_slopes == 0:
            # A single slope exceeds the height.
            return math.inf
        # Stacked slopes overlap in depth by 1 stud.
        remaining_depth = depth - (n_slopes * (slope_depth - 1) + 1)
        if remaining_depth == 0 and n_slopes * slope_height < height - BUILD_TOLERANCE:
            # Slopes exactly fill the depth but not the height,
            # so we cannot place bricks to fill the required height.
            return math.inf
        return remaining_depth if remaining_depth >= 0 else math.inf

    best = min(_slope_degrees(options), key=lambda dh: (score(*dh), *dh), default=None)
    return None if best is None or score(*best) == math.inf else best


def _slope_degrees(
    options: PartOptions,
) -> list[tuple[int, int]]:
    """List all slope degrees (depth, height) available in the catalog, sorted by steepness.

    Wedge filling stacks whole-brick slope courses, so slopes of a fractional height are skipped.
    """
    slopes = options.specs
    shapes = {s.shape for s in slopes if isinstance(s.shape, Box)}
    degrees = {(s.depth, int(s.height)) for s in shapes if s.height == int(s.height)}
    return sorted(degrees, key=lambda dh: dh[1] / dh[0])


def _single_slope(
    width: int,
    depth: int,
    height: Scalar,
    toward: Direction,
    color: Color,
    inverted: bool,
) -> LegoBuild | None:
    """A one-part model when dims match a real slope (incl. rotation and direction)."""
    if not isinstance(height, int):
        # Catalogued slopes all have integer heights.
        return None

    options, _ = _WEDGE_PARTS[inverted]
    spec = options.get(Box(*_horizontal_run(width, depth, toward), height))
    if spec is None:
        return None
    return _one(Element(spec.ldraw_id, color), _DESCENT_ROTATION[toward])


def _horizontal_run(width: int, depth: int, toward: Direction) -> tuple[int, int]:
    """(cross_len, run_len) for a wedge sloping horizontally ``toward``."""
    if toward in (Direction.FRONT, Direction.BACK):
        return width, depth
    return depth, width


def _one(element: Element, rotation: Rotation = Rotation.DEG_0) -> LegoBuild:
    """Builds a LegoBuild with a single element at the origin."""
    m = LegoBuild()
    m.add(element, Position.ZERO, rotation=rotation)
    return m
