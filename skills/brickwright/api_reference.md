# BrickLayer documentation

Build and validate LEGO models with catalog parts and reusable assemblies.

## Basic workflow

Find parts with `search_parts`, construct `Element(part_id, color)`, and place
with `LegoBuild.add`, `stack`, or `connect`. Each returns a `Placement` immediately.
Pass that placement (or its registered name) to subsequent calls.

```python
import bricklayer as bl

assembly = bl.LegoBuild()
base = assembly.add(bl.Element("3001", bl.Color.RED), name="base")
assembly.stack(bl.Element("3001", bl.Color.BLUE), on=base)

model = bl.LegoBuild()
model.add(assembly, (0, 0, 0), name="tower")
assert model.is_valid()
assert model.is_connected()
```

`is_valid()` means no collisions or floating parts; `is_connected()` means all
parts join through compatible connectors. A supported model can be valid while
containing several disconnected assemblies. Inspect `colliding_placements`,
`floating_placements`, and `connected_components` to diagnose problems.
Motion annotations do not change `is_valid()`: opt into `check_motion()` to
sample their ranges for collisions, floating, and connector disengagement.

## Geometry and coordinate conventions

The coordinate system is right-handed: +x points left, +y back, and +z up.
The ground is z=0. Width/depth are in studs; height is in bricks.
`PLATE` is one third of a brick. One brick is 6/5 of a stud: use
`Position.to_stud_units()` for uniform units when doing geometric calculations.

`add` and `stack` require integer x/y, z in whole plates, and quarter-turn
`Rotation`s about z. Use `connect` for sideways or offset connections;
`add_raw(content, pose)` accepts an arbitrary pose without grid checks.

### Local frames

Grid-marked parts are seated at their connector-defined bottom-center: a 4x2
brick's alignment box spans `(-2, -1, 0)` to `(2, 1, 1)`. For other parts,
inspect their connectors and boxes. A sub-model keeps the frame it was built in.
`add` rotates content, then anchors its rotated alignment box at the requested
position. `add_raw` applies the pose directly, without this re-anchoring.
`placement.pose.translation` is the placed local origin, which can differ from
the alignment-box corner passed to `add`.

The bounding box measures physical extent, including overhangs. The alignment
box determines grid placement and stacking; its rules are documented on
`LegoGeometry.alignment_box`. A model exposes only connectors not already mated
inside it, so covering its studs can change its alignment box.

Collisions use the parts' actual meshes. Touching or correctly mated surfaces
are allowed; intersecting parts are reported by `colliding_placements`.

### Classes

#### enum `Anchor`

Which corner, edge midpoint, or center of a footprint pins to a position.

**Members:** `FRONT_RIGHT`, `FRONT`, `FRONT_LEFT`, `RIGHT`, `CENTER`, `LEFT`, `BACK_RIGHT`, `BACK`, `BACK_LEFT`

#### enum `Axis`

A horizontal axis.

**Members:** `X`, `Y`

#### class `LegoGeometry`

Geometry shared by elements, placements, and models.

Elements use local coordinates; placements use the containing model's frame.
Models use the frame they were built in. Measurements update when content changes.

**Properties**

- `alignment_box: tuple[Position, Position]` -- The `(min, max)` box used for grid placement and stacking.

  Grid-aligned connectors contribute 1x1 stud footprints and determine the bottom.
  The highest upward stud sets the top; without one (e.g. a tile), the physical
  bounding box sets the top. Models use only their unoccupied connectors.

  Without grid-marked connectors, it is derived from the physical bounding box.
  Width/depth are whole studs and height is in whole plates; thin parts can
  have zero alignment extent. Inspect the box rather than guessing offsets.
- `alignment_depth: int` -- Extent along Y (studs) of the alignment box. Always an integer.
- `alignment_height: float` -- Extent along Z (bricks) of the alignment box. Always an integer multiple of PLATE.
- `alignment_width: int` -- Extent along X (studs) of the alignment box. Always an integer.
- `center: Position` -- The midpoint of the bounding box, in BrickLayer coordinates.

  Empty geometry returns ``Position(0, 0, 0)``.
- `depth: int | float` -- Extent along Y (studs) of the bounding box.
- `height: int | float` -- Extent along Z (bricks) of the bounding box.
- `width: int | float` -- Extent along X (studs) of the bounding box.

**Methods**

- `find_connector(connector_type: ConnectorType | str | Iterable[ConnectorType | str] | None = None, toward: Position | tuple[float, float, float] | Direction | None = None, *, facing: Direction | Vec3 | None = None) -> Connector` -- Find one connector using the filters and ordering of :meth:`find_connectors`.

  With ``toward``, return the first ranked match. Otherwise require exactly
  one match. Raises ``ValueError`` if none match or the choice is ambiguous.
  ``connect`` takes a world-frame target connector from a placement.
- `find_connectors(connector_type: ConnectorType | str | Iterable[ConnectorType | str] | None = None, toward: Position | tuple[float, float, float] | Direction | None = None, *, facing: Direction | Vec3 | None = None, count: int | None = None) -> list[Connector]` -- The geometry's connectors, filtered and ordered by the given criteria.

  ``connector_type`` filters types; ``facing`` filters axis direction.
  ``toward`` orders nearest a position or furthest in a direction; ``None``
  uses a stable geometric order. ``count`` caps the results (default: all).
  Coordinates are local for an element, world for a placement.
- `rotated_footprint(rotation: Rotation) -> tuple[int, int]` -- The alignment box's ``(width, depth)`` in studs after ``rotation``.

  An odd quarter turn swaps the two; a half turn leaves them as they are.

#### enum `Direction`

A face direction on the grid, valued as a unit displacement vector.

``UP``/``DOWN`` are the common stud / antistud facings; the lateral
directions describe side connectors (e.g. the studs on a bracket).
``LEFT`` is +x, ``BACK`` is +y.

**Members:** `UP`, `DOWN`, `BACK`, `FRONT`, `LEFT`, `RIGHT`

#### class `Mat3`

`Mat3(entries: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]) -> None`

A 3x3 matrix.

**Operators**

Supports `+`, `-`, `*`, `@`, unary `-`.

**Class constants**

- `IDENTITY` = `Mat3.IDENTITY`

**Properties**

- `entries: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]` -- The matrix rows, top to bottom.
- `transpose: Mat3` -- This matrix with its rows and columns swapped.

#### class `Position(Vec3)`

`Position(x: _T, y: _T, z: _T) -> None`

A position or offset in BrickLayer coordinates: ``x``/``y`` in studs, ``z`` (height) in *bricks*.

**Operators**

Supports `+`, `-`, `*`, `/`, unary `-`.

**Class constants**

- `ZERO` = `Position(0, 0, 0)`

**Methods**

- `align_to_grid() -> Position` -- Return a new position aligned to the integer build grid, flooring each
  coordinate to the grid (``x``/``y`` to whole studs, ``z`` to whole plates).
- `from_stud_units(v: Vec3 | Sequence[Scalar]) -> Position` (classmethod) -- Convert a vector in uniform stud units to a position in BrickLayer coordinates.
- `is_grid_aligned() -> bool` -- Check if the position is on the integer build grid (within tolerance).
- `to_stud_units() -> Vec3` -- This position as a plain vector in uniform stud units.

  Scales z by 6/5 for lengths, rotations, and other geometric calculations.

#### class `Pose`

`Pose(rotation: Mat3 = Mat3.IDENTITY, translation: Position = Position(0, 0, 0)) -> None`

An arbitrary rotation-then-translation in BrickLayer coordinates.

**Class constants**

- `IDENTITY` = `Pose(rotation=Mat3.IDENTITY, translation=Position(0, 0, 0))`

**Properties**

- `inverse: Pose` -- The pose that undoes this one: ``pose.inverse.compose(pose)`` is the identity.
- `rotation: Mat3`
- `translation: Position`

**Methods**

- `apply(p: Position | Sequence[Position]) -> Position | tuple[Position, ...]` -- Map position(s) through this pose.
- `compose(other: Pose) -> Pose` -- The pose applying ``other`` first, then ``self``.
- `from_rotation(rotation: Rotation) -> Pose` (classmethod) -- A pose that applies ``rotation`` (a quarter-turn about z) with no translation.

#### enum `Rotation`

A rotation about the vertical axis, in 90-degree steps.

The value is the number of quarter-turns counter-clockwise when viewed from
above (down the +Z axis).

The "facing" aliases ``FRONT``/``RIGHT``/``BACK``/``LEFT`` name where the
side that usually faces front (-y) ends up: ``BACK`` is a half turn,
``LEFT`` a counter-clockwise quarter turn (which sends the front side to
the left), and ``RIGHT`` the opposite quarter turn.

**Members:** `DEG_0`, `DEG_90`, `DEG_180`, `DEG_270`, `FRONT`, `LEFT`, `BACK`, `RIGHT`

**Operators**

Supports `+`, `-`, `*`, unary `-`.

**Properties**

- `matrix: Mat3` -- Return the 3x3 matrix representing this rotation.

**Methods**

- `rotate(v: VecType) -> VecType` -- Apply this rotation about the vertical (+z) axis to a vector.

#### class `Vec3`

`Vec3(x: _T, y: _T, z: _T) -> None`

A 3-component vector with componentwise arithmetic.

Concrete coordinate classes subclass this, one per coordinate system;
``+``/``-`` require both operands to be the *same* class, so vectors from
different coordinate systems cannot be combined by accident.

**Operators**

Supports `+`, `-`, `*`, `/`, unary `-`.

**Properties**

- `x: _T`
- `y: _T`
- `z: _T`

**Methods**

- `norm() -> float` -- The Euclidean norm (length) of this vector.

### Functions

#### `rotation_about(axis: Vec3, degrees: float) -> Mat3`

The right-handed rotation by ``degrees`` about the unit vector ``axis``.

Multiples of 90 degrees produce exact (integer) matrices; other angles use
floats (Rodrigues' rotation formula).

#### `to_bricks(plates: int) -> float`

Convert integer plate-heights to a height in bricks.

#### `to_plates(bricks: HeightLike, *, round_down: bool = False) -> int`

Convert a height/elevation in bricks to integer plate-heights.

If ``round_down`` is True, the result is rounded down to the nearest plate;
otherwise, ``bricks`` must be a multiple of 1/3 (1 plate).

### Constants

- `PLATE` = `0.3333333333333333`
- `HeightLike` = `int | float | Fraction`

## Connections

Parts attach through compatible connector types: studs/antistuds, clips/bars,
axles/holes, ball joints, and others. Use existing connectors rather than creating
types or mating rules. Common names include `stud`, `antistud`, `bar`, `clip`,
`axle`, `axle_hole`, `pin`, `pin_hole`, `towball`, and `towball_socket`.
`stud` also matches hollow studs; `antistud` includes underside tubes.
Inspect a part's `connectors` to discover other types.

### Mounting and motion

`connect` fits compatible connectors; incompatible types raise `ValueError`.
`Mounting(angle=..., offset=..., flip=...)` chooses a fixed assembly pose.
Angles are degrees and sliding offsets are studs. Ball mounting additionally
accepts `swing_x` and `swing_y` in the connector frame; `angle` is its twist.
`target_rotation` requests the part's orientation and `target_position` its
connector's world position. Explicit mounting is applied after fitting them.

Connections are static unless given a `MotionRange`. Joint coordinates describe
motion from the mounted pose; see the recorded connections and motion section
for range declarations, pose previews, and validation.

### Connecting parts

Use `LegoBuild.add` or `stack` for grid-aligned stud connections; couplings are
detected automatically.

`LegoBuild.connect` mates a local connector on `content` to a world-frame target
from a placement. The source can be a `Connector` or a type/name identifying
its unique connector.

```python
import bricklayer as bl

model = bl.LegoBuild()
socket_part = model.add(bl.Element("14418", bl.Color.WHITE), name="socket_part")
model.connect(
    bl.Element("22890", bl.Color.WHITE),
    "towball",  # the connector type on the ball part
    to=socket_part.find_connector("towball_socket"),
    target_rotation=bl.rotation_about(bl.Direction.UP.value, 180),
    mounting=bl.Mounting(swing_x=5),
)
assert model.is_valid() and model.is_connected()
```

When several source connectors share a type, select one with `find_connector`
and pass it directly:

```python
import bricklayer as bl

link = bl.Element("3170", bl.Color.WHITE)
far_conn = link.find_connector("towball", toward=bl.Direction.LEFT)  # the +x ball

model = bl.LegoBuild()
socket_part = model.add(bl.Element("14418", bl.Color.WHITE), name="socket_part")
model.connect(link, far_conn, to=socket_part.find_connector("towball_socket"))
```

### Breaking away from the stud build grid

Use `connect()` with SNOT (Studs Not On Top) bricks or brackets to build sideways.
Select side studs with `facing`; use `toward` to choose among several matches.

```python
import bricklayer as bl

base = bl.Element("11211", bl.Color.WHITE)
attachment = bl.plate(1, 1)
mount = attachment.find_connector("antistud")

model = bl.LegoBuild()
placed_base = model.add(base, name="base")
# Select the leftmost front-facing stud in the model's frame.
side_stud = placed_base.find_connector(
    "stud", facing=bl.Direction.FRONT, toward=bl.Direction.LEFT
)
model.connect(attachment, mount, to=side_stud)
assert model.is_valid() and model.is_connected()
```

Use `connect()` with jumper studs for half-stud offsets:

```python
import bricklayer as bl

base = bl.Element("15573", bl.Color.WHITE)
attachment = bl.plate(1, 1)
mount = attachment.find_connector("antistud")

model = bl.LegoBuild()
jumper = model.add(base, name="jumper")
# Select the offset top stud in the model's frame.
offset_stud = jumper.find_connector("stud", facing=bl.Direction.UP)
model.connect(attachment, mount, to=offset_stud)
assert model.is_valid() and model.is_connected()
```

### Classes

#### class `Connector`

A mating point obtained from a part or placement's connectors.

`position` is in the queried geometry's frame. `axis` is its mating direction;
`side` fixes its roll. Both directions use uniform stud units.
`length` is the sliding reach in studs on either side of the point.

**Properties**

- `axis: Vec3`
- `length: Scalar`
- `position: Position`
- `side: Vec3`
- `type: ConnectorType`

#### class `ConnectorType`

A registered connector kind, identified by `name`.

Use names or `get_connector_type(name)` to select existing types.

**Properties**

- `name: str`

#### enum `JointKind`

Continuous degrees of freedom of a joint.

**Members:** `FIXED`, `REVOLUTE`, `PRISMATIC`, `CYLINDRICAL`, `BALL`

#### class `Mounting`

`Mounting(angle: float = 0.0, offset: Scalar = 0, flip: bool = False, swing_x: float = 0.0, swing_y: float = 0.0) -> None`

Assembly choices, fixed once connected.

``angle`` is clocking about the connector axis (degrees), ``offset`` is
insertion along it (studs), and ``flip`` turns an axial connection end for
end. Ball mounting uses ``swing_x``/``swing_y`` as a rotation vector in the
connector's transverse plane, followed by ``angle`` as twist, in degrees.

**Properties**

- `angle: float`
- `flip: bool`
- `offset: Scalar`
- `swing_x: float`
- `swing_y: float`

#### class `Fixed`

`Fixed() -> None`

A joint with no motion coordinates.

#### class `Revolute`

`Revolute(angle: float = 0.0) -> None`

Rotation from the mounted pose about the joint axis, in degrees.

**Properties**

- `angle: float`

#### class `Prismatic`

`Prismatic(offset: Scalar = 0) -> None`

Translation from the mounted pose along the joint axis, in studs.

**Properties**

- `offset: Scalar`

#### class `Cylindrical`

`Cylindrical(offset: Scalar = 0, angle: float = 0.0) -> None`

Sliding (studs) and rotation (degrees) from the mounted pose.

**Properties**

- `angle: float`
- `offset: Scalar`

#### class `Ball`

`Ball(swing_x: float = 0.0, swing_y: float = 0.0, twist: float = 0.0) -> None`

Joint-local swing and twist, in degrees, from the mounted pose.

The swing is the rotation vector ``(swing_x, swing_y, 0)`` about the joint's
transverse axes. Its length is the swing angle. The orientation is
``swing @ twist_about_z``. This convention follows the joint when the whole
model turns; it does not use world Euler angles.

**Properties**

- `swing_x: float`
- `swing_y: float`
- `twist: float`

### Functions

#### `get_connector_type(name: str) -> ConnectorType`

The :class:`ConnectorType` registered under ``name``; e.g. ``"stud"``.

## Exploring the catalog

Use `search_parts` to find a part, then build `Element(spec.ldraw_id, color)`.
Keyword terms all have to match whole words; filters require exact property values.
Common parts rank higher using set counts from Rebrickable's catalogue.

```python
import bricklayer as bl

# Keywords may match "door" in any default text field; category is an exact filter.
doors = bl.search_parts("door", category="Door", limit=4)
assert all(spec.category == "Door" for spec in doors)
plates = bl.search_parts(category="Plate", shape=bl.Footprint(6, 2), limit=4)
assert all(spec.shape == bl.Footprint(6, 2) for spec in plates)
```

`PartSpec` describes a catalog part; unknown ids are rejected. Shape information
can be absent: use an element's measured bounding box for physical dimensions.

### Dimensions and names

API dimensions are **width-first** (x, then y); slopes run along their depth (y).
LDraw names are preserved verbatim and their dimension order varies by category.
For example, `Plate  2 x  6` has `Footprint(6, 2)`, but `Wing  2 x  6 Left`
has `Footprint(2, 6)`. Use `spec.shape` or measured geometry rather than inferring
API dimensions from a name. LEGO's "Slope 45 2 x 3" is a 3x2 slope in the API.

### Classes

#### class `PartSpec`

`PartSpec(ldraw_id: str) -> None`

A catalog part identified by its LDraw id; unknown ids are rejected.

Properties describe its LDraw name and nominal shape. `subcategory`, `features`,
`chirality`, and `shape` can be `None` when that information is absent.
Parts without connectors can rest on the ground but cannot attach to others.

**Properties**

- `category: str` -- The part category, e.g. "Brick" or "Minifig".
- `chirality: Chirality | None` -- The part's handedness, or ``None`` if achiral.
- `features: str | None` -- The part's ``with ...`` clause, e.g. "with Groove".
- `ldraw_id: str`
- `mirrored: PartSpec` -- This part's mirror image: the same part in the opposite :attr:`chirality`.

  ``spec.mirrored is spec`` when there is none -- the part is achiral, or
  the catalog holds only its one hand.
- `name: str` -- The part's LDraw name, e.g. "Brick  1 x  1".
- `shape: PartShape | None` -- Nominal dimensions, or `None` if no reliable shape is known.

  Use the element's bounding box when you need its measured physical extent.
- `subcategory: str | None` -- The subtype around the name's dimensions, e.g. "Round Half Circle".

#### class `PartShape`

A part's nominal dimensions, used in catalog search filters.

Concrete shapes specify their units below. Missing shape information does not
prevent construction; use an element's bounding box for its measured extent.

#### class `Box(PartShape)`

`Box(width: int, depth: int, height: HeightLike) -> None`

A rectangular solid, ``width`` studs x ``depth`` studs x ``height`` bricks.

``height`` is quantized to whole plates (1/3 brick), so ``5/3`` and
``Fraction(5, 3)`` name the same box.

#### class `Disc(PartShape)`

`Disc(diameter: int) -> None`

A round flat part, ``diameter`` studs across, with a fixed height (e.g., a round plate or a dish).

#### class `Footprint(PartShape)`

`Footprint(width: int, depth: int) -> None`

A flat part, ``width`` x ``depth`` studs, with a fixed height (e.g., a plate or tile).

#### class `Pane(PartShape)`

`Pane(width: int, height: HeightLike) -> None`

A thin standing sheet: ``width`` studs x ``height`` bricks.

``height`` is quantized to whole plates (1/3 brick).

#### class `Ell(PartShape)`

`Ell(width: int, depth: int, face_width: int, face_height: int) -> None`

An L-shaped part: a flat plate with a studded SNOT flange along the front edge.

The plate is ``width`` x ``depth`` studs; the flange is ``face_width`` studs
across and ``face_height`` studs **tall**.

A flange's height is measured in studs, so the part is not in general a whole number of plates tall.

#### class `Length(PartShape)`

`Length(length: HeightLike) -> None`

A part measured only along its own axis (e.g. Technic beams): ``length`` studs long.

``length`` is normalized to an exact ``Fraction``, so ``1.5`` and ``Fraction(3, 2)`` name the same length.

#### class `Rod(PartShape)`

`Rod(diameter: int, height: HeightLike) -> None`

A round brick: ``diameter`` studs across and ``height`` bricks tall.

``height`` is quantized to whole plates (1/3 brick).

#### enum `Chirality`

The handedness of a chiral part.

**Members:**
- `LEFT` -- Left-handed variant.
- `RIGHT` -- Right-handed variant.

**Properties**

- `opposite: Chirality` -- The other handedness.

### Functions

#### `search_parts(*terms: str, fields: str | Iterable[str] | None = None, limit: int = 20, **filters: Any) -> tuple[PartSpec, ...]`

Find catalog parts by keywords and exact property filters.

All keyword terms must match whole words; phrases split into words.
`fields` selects text fields: `name`, `category`, `subcategory` by default;
`features` can be requested explicitly. Results favor common parts using
Rebrickable set counts. With no keywords, rank by popularity alone.

Filters accept any `PartSpec` property, e.g. `category="Tile"` or
`shape=Box(4, 2, 1)`. Return at most `limit` results, best first.
An unknown field/filter, empty `fields`, or negative `limit` raises `ValueError`.

#### `part_exists(part_id: str) -> bool`

Whether the catalog holds the LDraw part ``part_id``.

The non-raising counterpart to ``PartSpec(part_id)``.

## Creating LEGO components

A part is a LEGO piece; an `Element` adds its color. Construct any catalogued part
with `Element(part_id, color)`, including specialized parts without a size helper.
A `LegoBuild` groups elements into a reusable assembly.

```python
import bricklayer as bl

ladder = bl.Element("4175", bl.Color.RED)
```

### Classes

#### class `Element(LegoGeometry)`

`Element(ldraw_id: str, color: Color | LDrawColor) -> None`

A catalogued part in a color, constructed as `Element(part_id, color)`.

Elements are immutable; matching part ids and colors compare equal.

**Properties**

- `bounding_box: tuple[Position, Position]` -- Physically-measured `(min, max)` box in the local frame.
- `color: Color | LDrawColor` -- The element's color.
- `connectors: frozenset[Connector]` -- Points where a connection can be made, in the local frame.
- `ldraw_id: str` -- The part's LDraw id.
- `spec: PartSpec` -- The part's catalog identity, resolved from its id.

## Component factories

Optional helpers select basic parts by size or assemble windows, doors, and
minifigures. They return ordinary elements or models. Size helpers accept only
the generated argument combinations listed below; rotate a supported size when
needed. Use `Element(part_id, color)` for other catalog parts.

### `brick(width: int, depth: int, height: HeightLike = 1, color: Color = Color.WHITE) -> Element`

A solid rectangular brick, the most basic LEGO part.

The brick has a base of ``width`` x ``depth`` studs and is ``height`` bricks tall.
Studs cover its top, and antistuds cover its bottom.

Raises:
    ValueError: if the given arguments do not yield a valid part.

#### Valid argument combinations `(width, depth, height)`

- `(1, 1, 1)`
- `(1, 1, 3)`
- `(1, 1, 5)`
- `(2, 1, 1)`
- `(2, 1, 2)`
- `(2, 1, 3)`
- `(2, 1, 5)`
- `(2, 2, 1)`
- `(2, 2, 3)`
- `(3, 1, 1)`
- `(3, 2, 1)`
- `(4, 1, 1)`
- `(4, 1, 3)`
- `(4, 2, 1)`
- `(6, 1, 1)`
- `(6, 2, 1)`
- `(8, 1, 1)`
- `(8, 2, 1)`
- `(10, 1, 1)`
- `(10, 2, 1)`
- `(12, 1, 1)`
- `(16, 1, 1)`

### `door(width: int, depth: int, height: int | float | Fraction, door_variant: DoorVariant = DoorVariant.SOLID, frame_variant: FrameVariant | None = None, door_color: Color = Color.WHITE, frame_color: Color = Color.WHITE, open_angle: float = 0.0) -> LegoBuild`

A filled doorway: a frame plus the hinged door leaf inside it.

The result is a small :class:`LegoBuild` assembly -- the frame element plus
a door element (its own LDraw part and color) placed inside it.

``open_angle`` swings the leaf open on its hinge, in degrees from 0 (closed)
to 90 (fully open). A door cannot go in a :attr:`~FrameVariant.THREE_PANES` frame,
whose muntins block the swing.

Raises:
    ValueError: if the given arguments do not yield a valid frame,
    a door of the given variant is not available for the frame,
    ``open_angle`` is outside 0-90 degrees, or the frame is
    muntined (a :attr:`~FrameVariant.THREE_PANES` variant).
    TypeError: if ``door_variant`` is not a :class:`DoorVariant`.

#### Valid argument combinations `(width, depth, height, door_variant, frame_variant)`

- `(4, 1, 6, DoorVariant.SOLID, None)`
- `(4, 1, 6, DoorVariant.GLASS, None)`
- `(4, 1, 6, DoorVariant.WINDOWED, None)`
- `(4, 1, 6, DoorVariant.PET, None)`
- `(4, 1, 6, DoorVariant.GRILLE, None)`
- `(4, 2, 6, DoorVariant.SOLID, None)`
- `(4, 2, 6, DoorVariant.GLASS, None)`
- `(4, 2, 6, DoorVariant.WINDOWED, None)`
- `(4, 2, 6, DoorVariant.PET, None)`
- `(4, 2, 6, DoorVariant.GRILLE, None)`
- `(4, 4, 6, DoorVariant.SOLID, FrameVariant.ANGLED_CORNER)`
- `(4, 4, 6, DoorVariant.GLASS, FrameVariant.ANGLED_CORNER)`
- `(4, 4, 6, DoorVariant.WINDOWED, FrameVariant.ANGLED_CORNER)`
- `(4, 4, 6, DoorVariant.PET, FrameVariant.ANGLED_CORNER)`
- `(4, 4, 6, DoorVariant.GRILLE, FrameVariant.ANGLED_CORNER)`

### `inverted_slope(width: int, depth: int, height: int | float | Fraction = 1, color: Color = Color.WHITE) -> Element`

A brick with an angled underside.

The part has a base of ``width`` x ``depth`` studs and is ``height`` bricks tall.
The slope runs along the Y-axis (depth). It starts at `height` at the front
edge of the front row (y=0, z=height) and reaches ground level at the front
edge of the back row (y=depth-1, z=0). Studs cover the top; antistuds sit only
on the underside of the back row.

Raises:
    ValueError: if the given arguments do not yield a valid part.

#### Valid argument combinations `(width, depth, height)`

- `(1, 2, 1)`
- `(1, 2, 3)`
- `(1, 3, 1)`
- `(2, 2, 1)`
- `(2, 3, 1)`

### `minifig(*, head_id: str = '3626bp01', torso_id: str = '973', hips_id: str | None = None, left_leg_id: str | None = None, right_leg_id: str | None = None, legs_id: str | None = None, skin_color: Color = Color.YELLOW, torso_color: Color = Color.WHITE, arm_color: Color | None = None, hand_color: Color | None = None, leg_color: Color = Color.WHITE, hips_color: Color | None = None, headwear_id: str | None = None, headwear_color: Color = Color.WHITE, bodywear_id: str | None = None, bodywear_color: Color = Color.WHITE, footwear_id: str | None = None, footwear_color: Color = Color.WHITE, pose: MinifigPose | None = None) -> LegoBuild`

Assemble a minifigure as a :class:`LegoBuild`.

Minifigures are typically 2 studs wide, 1 stud deep, and 4 bricks tall.
Select printed faces and clothing with ``head_id`` and ``torso_id``. Use
``hips_id``, ``left_leg_id``, and ``right_leg_id`` for separate lower-body
parts, or ``legs_id`` for a single-piece lower body. Find ids with
``search_parts``; the supplied parts must carry compatible connectors.
Defaults assemble the standard smiling head, plain torso, and articulated legs.

Select accessories with ``headwear_id``, ``bodywear_id``, and ``footwear_id``.
Their ``headwear_color``, ``bodywear_color``, and ``footwear_color`` arguments
default to white. ``pose`` controls the joints; single-piece legs cannot swing.

The minifig is translated to the ground plane (z=0) after construction.
Hence, if both legs are swung 90 degrees forward, the figure will end up sitting on the ground.

Colors: ``skin_color`` is the head; ``arm_color`` defaults to ``torso_color``,
``hand_color`` to ``skin_color``, and ``hips_color`` to ``leg_color``.


Raises:
    ValueError: if an accessory lacks the required attachment connector,
    ``pose`` articulates single-piece legs, separate and single-piece lower
    bodies are selected together, or footwear cannot attach to two soles.

### `minifig_body(torso_color: Color = Color.WHITE, arm_color: Color | None = None, hand_color: Color = Color.YELLOW, pose: MinifigPose | None = None, *, torso_id: str = '973', bodywear_id: str | None = None, bodywear_color: Color = Color.WHITE) -> LegoBuild`

A minifig body (torso, arms, and hands), plus an optional body accessory worn around the neck peg.

Select printed clothing with ``torso_id`` and an accessory with ``bodywear_id``.
``bodywear_color`` defaults to white.
To build a full minifig, use :func:`minifig`.

Raises:
    ValueError: if the torso or accessory lacks a required attachment connector.

### `minifig_head(color: Color = Color.YELLOW, *, head_id: str = '3626bp01', headwear_id: str | None = None, headwear_color: Color = Color.WHITE) -> LegoBuild`

A minifig head piece with an optional accessory worn on its crown stud.

Select the head with ``head_id`` and its accessory with ``headwear_id``.
``headwear_color`` defaults to white; printed faces are ordinary catalog parts.
To build a full minifig, use :func:`minifig`.

Raises:
    ValueError: if the head lacks a neck socket or the accessory lacks an antistud connector.

### `minifig_legs(leg_color: Color = Color.WHITE, hips_color: Color | None = None, pose: MinifigPose | None = None, *, hips_id: str | None = None, left_leg_id: str | None = None, right_leg_id: str | None = None, legs_id: str | None = None, footwear_id: str | None = None, footwear_color: Color = Color.WHITE) -> LegoBuild`

Assemble a minifigure lower body from catalog parts, with optional footwear.

Choose separate ``hips_id``, ``left_leg_id``, and ``right_leg_id`` values,
or a single-piece lower body with ``legs_id``. Omitted separate parts use
the standard hips and articulated legs. Explicit leg ids are used in their
given handedness, so select a left leg for ``left_leg_id``.

``hips_color`` defaults to ``leg_color``. A single-piece lower body uses
``leg_color``. Choose footwear with ``footwear_id`` and ``footwear_color``
(white by default). It requires one sole on each leg, or two soles on the
single-piece lower body.

Raises:
    ValueError: if ``legs_id`` is combined with separate part ids, a pose
        articulates single-piece legs, or a part lacks attachment connectors.

### `plate(width: int, depth: int, color: Color = Color.WHITE) -> Element`

A thin rectangular plate, one third of a brick tall.

The plate has a base of ``width`` x ``depth`` studs and a height of one plate (1/3 of a brick).
Like a brick, studs cover its top and antistuds cover its bottom.

Raises:
    ValueError: if the given arguments do not yield a valid part.

#### Valid argument combinations `(width, depth)`

- `(1, 1)`
- `(2, 1)`
- `(2, 2)`
- `(3, 1)`
- `(3, 2)`
- `(3, 3)`
- `(4, 1)`
- `(4, 2)`
- `(4, 4)`
- `(5, 1)`
- `(6, 1)`
- `(6, 2)`
- `(6, 4)`
- `(6, 6)`
- `(8, 1)`
- `(8, 2)`
- `(8, 4)`
- `(8, 6)`
- `(8, 8)`
- `(10, 1)`
- `(10, 2)`
- `(10, 4)`
- `(10, 6)`
- `(12, 1)`
- `(12, 2)`
- `(12, 4)`
- `(12, 6)`
- `(14, 2)`
- `(14, 6)`
- `(16, 2)`
- `(16, 6)`
- `(16, 8)`
- `(16, 16)`

### `slope(width: int, depth: int, height: int | float | Fraction = 1, color: Color = Color.WHITE) -> Element`

A brick with an angled top, ideal for roofs.

The part has a base of ``width`` x ``depth`` studs and is ``height`` bricks tall.
The slope runs along the Y-axis (depth). It starts at ground level at the
front edge of the front row (y=0, z=0) and reaches `height` at the front edge
of the back row (y=depth-1, z=height). Studs sit only on the back row's flat top;
antistuds cover the underside.

Raises:
    ValueError: if the given arguments do not yield a valid part.

#### Valid argument combinations `(width, depth, height)`

- `(1, 2, 1)`
- `(1, 2, 2)`
- `(1, 2, 3)`
- `(1, 3, 1)`
- `(1, 4, 1)`
- `(1, 8, 3)`
- `(2, 2, 1)`
- `(2, 2, 2)`
- `(2, 2, 3)`
- `(2, 3, 1)`
- `(2, 4, 1)`
- `(3, 2, 1)`
- `(3, 3, 1)`
- `(4, 2, 1)`
- `(4, 3, 1)`
- `(6, 2, 1)`
- `(8, 2, 1)`

### `tile(width: int, depth: int, color: Color = Color.WHITE) -> Element`

A thin rectangular tile: like a plate, but with a smooth top (no studs). Ideal for finishing surfaces.

Raises:
    ValueError: if the given arguments do not yield a valid part.

#### Valid argument combinations `(width, depth)`

- `(1, 1)`
- `(2, 1)`
- `(2, 2)`
- `(3, 1)`
- `(3, 2)`
- `(4, 1)`
- `(4, 2)`
- `(4, 4)`
- `(6, 1)`
- `(6, 2)`
- `(6, 6)`
- `(8, 1)`
- `(16, 8)`

### `window(width: int, depth: int, height: int | float | Fraction, pane_variant: PaneVariant = PaneVariant.SOLID, frame_variant: FrameVariant | None = None, pane_color: Color = Color.WHITE, frame_color: Color = Color.WHITE) -> LegoBuild`

A filled window: a frame plus the window pane(s) inside it.

The result is a small :class:`LegoBuild` assembly -- the frame element
plus pane element(s) placed inside it. Certain frames carry multiple pane elements.

Raises:
    ValueError: if the given arguments do not yield a valid frame, or a pane
        of the given variant is not available for the frame.
    TypeError: if ``pane_variant`` is not a :class:`PaneVariant`.

#### Valid argument combinations `(width, depth, height, pane_variant, frame_variant)`

- `(2, 1, 2, PaneVariant.SOLID, None)`
- `(2, 1, 2, PaneVariant.LATTICE, None)`
- `(2, 1, 2, PaneVariant.SOLID, FrameVariant.AIRPLANE)`
- `(2, 1, 2, PaneVariant.LATTICE, FrameVariant.AIRPLANE)`
- `(2, 1, 2, PaneVariant.SOLID, FrameVariant.ARCHED)`
- `(2, 1, 2, PaneVariant.LATTICE, FrameVariant.ARCHED)`
- `(2, 1, 3, PaneVariant.SOLID, None)`
- `(2, 1, 3, PaneVariant.SOLID, FrameVariant.TRAIN)`
- `(3, 1, 3, PaneVariant.SOLID, None)`
- `(4, 1, 3, PaneVariant.SOLID, None)`
- `(4, 1, 6, PaneVariant.SOLID, None)`
- `(4, 1, 6, PaneVariant.SOLID, FrameVariant.THREE_PANES)`
- `(4, 2, 3, PaneVariant.SOLID, None)`
- `(4, 2, 6, PaneVariant.SOLID, None)`
- `(4, 2, 6, PaneVariant.GRILLE, None)`
- `(4, 4, 3, PaneVariant.SOLID, FrameVariant.SLOPED)`
- `(4, 4, 6, PaneVariant.SOLID, FrameVariant.ANGLED_CORNER)`

### Classes

#### class `MinifigPose`

`MinifigPose(head: float = 0.0, left_arm: float = 0.0, right_arm: float = 0.0, left_hand: float = 0.0, right_hand: float = 0.0, left_leg: float = 0.0, right_leg: float = 0.0) -> None`

Joint angles articulating a minifigure, in degrees; zero is the neutral
standing pose.

``head`` turns the head about the neck peg (positive toward the figure's
own left). Arms swing about the shoulder axes and legs about the hip pins
(positive swings the limb forward). Hands rotate about their wrist pegs
(positive swings the fingers outward, away from the body).

A hip pin only travels so far: a leg may swing up to
:data:`LEG_FORWARD_LIMIT` degrees forward and :data:`LEG_BACKWARD_LIMIT`
degrees back; angles outside that range raise :class:`ValueError`.

**Class constants**

- `LEG_BACKWARD_LIMIT` = `45.0`
- `LEG_FORWARD_LIMIT` = `90.0`

**Properties**

- `head: float`
- `left_arm: float`
- `left_hand: float`
- `left_leg: float`
- `right_arm: float`
- `right_hand: float`
- `right_leg: float`

#### enum `FrameVariant(PartVariant)`

A window frame variant. ``None`` means a plain rectangular frame.

Some variants (ARCHED, THREE_PANES, AIRPLANE, TRAIN) only change the shape of the opening,
while others (SLOPED, ANGLED_CORNER, ROUND_CORNER) change the geometry of the frame itself.

**Members:**
- `ARCHED` -- A window frame with a rounded (arched) top.
- `THREE_PANES` -- A window frame divided into three panes.
- `AIRPLANE` -- A rounded window frame, ideal for an airplane fuselage.
- `TRAIN` -- A rounded window frame, ideal for a train car.
- `SLOPED` -- Slopes down back to front, forming a 45-degree angle with the vertical.
- `ANGLED_CORNER` -- Forms a 45-degree corner.
- `ROUND_CORNER` -- Curves around a corner.

#### enum `PaneVariant(PartVariant)`

A window pane: the insert that fills a frame in a :func:`window`.

**Members:**
- `SOLID` -- A solid pane, typically in a transparent color to represent glass.
- `LATTICE` -- An elegant pane of crisscrossing diagonal strips.
- `GRILLE` -- A pane of vertical and horizontal slats, like a jail cell window.

#### enum `DoorVariant(PartVariant)`

A door leaf: the insert that fills a frame in a :func:`door`.

**Members:**
- `SOLID` -- A plain, solid hinged door.
- `GLASS` -- A glass door with three panes.
- `WINDOWED` -- A classic house door with a four-pane window.
- `PET` -- A door with a six-pane window and a pet flap at the bottom.
- `GRILLE` -- A hinged door with vertical and horizontal slats, like a jail cell.

### Available colors (pass any as a `color=` argument)

`Color` is a closed enum. The available colors below are grouped by surface finish.

#### Solid

Opaque plastic with a smooth surface -- the default for most bricks.

`Color.BLACK`, `Color.WHITE`, `Color.LIGHT_BLUISH_GRAY`, `Color.DARK_BLUISH_GRAY`, `Color.RED`, `Color.YELLOW`, `Color.BLUE`, `Color.REDDISH_BROWN`, `Color.TAN`, `Color.GREEN`, `Color.ORANGE`, `Color.DARK_TAN`, `Color.DARK_BLUE`, `Color.LIME`, `Color.DARK_RED`, `Color.MEDIUM_NOUGAT`, `Color.MEDIUM_AZURE`, `Color.BRIGHT_LIGHT_ORANGE`, `Color.BRIGHT_GREEN`, `Color.DARK_ORANGE`, `Color.DARK_BROWN`, `Color.DARK_TURQUOISE`, `Color.DARK_GREEN`, `Color.BRIGHT_PINK`, `Color.LIGHT_NOUGAT`, `Color.DARK_PURPLE`, `Color.DARK_AZURE`, `Color.SAND_GREEN`, `Color.DARK_PINK`, `Color.MAGENTA`, `Color.BRIGHT_LIGHT_YELLOW`, `Color.MEDIUM_BLUE`, `Color.MEDIUM_LAVENDER`, `Color.LIGHT_AQUA`, `Color.BRIGHT_LIGHT_BLUE`, `Color.SAND_BLUE`, `Color.OLIVE_GREEN`, `Color.LAVENDER`, `Color.CORAL`, `Color.NOUGAT`, `Color.YELLOWISH_GREEN`, `Color.REDDISH_ORANGE`, `Color.VIBRANT_YELLOW`, `Color.WARM_TAN`, `Color.MEDIUM_BROWN`, `Color.BLUE_VIOLET`, `Color.SKY_BLUE`, `Color.SIENNA_BROWN`, `Color.WARM_PINK`, `Color.UMBER_BROWN`

#### Transparent

See-through, translucent plastic used for glass, water, and light effects.

`Color.TRANS_CLEAR`, `Color.TRANS_LIGHT_BLUE`, `Color.TRANS_RED`, `Color.TRANS_ORANGE`, `Color.TRANS_YELLOW`, `Color.TRANS_DARK_BLUE`, `Color.TRANS_BROWN`, `Color.TRANS_NEON_GREEN`, `Color.TRANS_GREEN`, `Color.TRANS_DARK_PINK`, `Color.TRANS_NEON_ORANGE`, `Color.TRANS_BRIGHT_GREEN`, `Color.TRANS_PURPLE`, `Color.TRANS_BLACK`

#### Opalescent

Translucent plastic with a milky opal sheen.

`Color.OPAL_TRANS_LIGHT_BLUE`, `Color.OPAL_TRANS_CLEAR`, `Color.OPAL_TRANS_PURPLE`, `Color.OPAL_TRANS_DARK_PINK`, `Color.OPAL_TRANS_DARK_BLUE`, `Color.OPAL_TRANS_BRIGHT_GREEN`, `Color.OPAL_TRANS_BROWN`

#### Glitter

Translucent plastic infused with fine reflective flakes that sparkle.

`Color.GLITTER_TRANS_PURPLE`, `Color.GLITTER_TRANS_DARK_PINK`, `Color.GLITTER_TRANS_LIGHT_BLUE`, `Color.GLITTER_TRANS_CLEAR`

#### Pearl

Opaque plastic with a pearlescent sheen, duller than Metallic.

`Color.PEARL_GOLD`, `Color.PEARL_SILVER`, `Color.PEARL_TITANIUM`, `Color.PEARL_WHITE`

#### Metallic

Opaque plastic with a metallic shimmer, shinier than Pearl.

`Color.METALLIC_GOLD`, `Color.METALLIC_SILVER`

#### Chrome

A mirror-like metal coating electroplated onto the plastic. Even shinier and more reflective than Metallic.

`Color.CHROME_GOLD`, `Color.CHROME_SILVER`

#### Glow

Phosphorescent plastic that absorbs light and glows in the dark.

`Color.GLOW_IN_DARK_WHITE`

## Building a LEGO model

Nested models are held by reference: editing a shared sub-model changes every
assembly that contains it.
`copy()` shares these sub-models; `deepcopy()` isolates them.

Relative placement reads the reference's geometry at call time. Later changes
to the reference do not move already placed parts.

Names can be paths: `model.named(["tower", "roof"])` returns the roof placement
in the outer model's coordinate frame. Returned placements can be used with
`relative_to` or `on`. Remove a placement and place another to change its pose.

Placement methods append by default; `index` inserts before a top-level position
(negative indices count from the end).

### Classes

#### class `Placement(LegoGeometry)`

An element or sub-model placed in a containing model.

`content` and `pose` are fixed. Geometry is expressed in the containing model's
frame and updates if the content is a mutable sub-model. Placements compare by
identity; two placements can hold identical elements at different positions.

**Properties**

- `bounding_box: tuple[Position, Position]` -- The content's physical bounding box, in world coordinates.
- `connectors: frozenset[Connector]` -- The content's connector points, in world coordinates.
- `pose: Pose` -- Maps the content's local frame into the model's.

**Methods**

- `to_world(p: Position | tuple[float, float, float]) -> Position` -- Map a position from the content's local frame to world coordinates.

#### class `LegoBuild(LegoGeometry)`

`LegoBuild(placements: Iterable[Placement] = (), names: Mapping[str, Placement] | None = None, steps: Iterable[int] | None = None, *, joints: Iterable[Joint] = ()) -> None`

A build or reusable sub-assembly, edited in place.

Validity queries update automatically after edits, including edits to nested
models. `is_valid` checks collisions and ground support; `is_connected` checks
whether every part joins through compatible connectors.

**Properties**

- `bounding_box: tuple[Position, Position]` -- The physical bounding box spanning every part's, in the model's frame.

  A sub-model holding no parts spans nothing, so a model with no parts
  returns ``(Position.ZERO, Position.ZERO)``.
- `brick_count: int` -- The total number of bricks in the model.
- `colliding_placements: tuple[tuple[Placement[Element], Placement[Element]], ...]` -- Pairs of placements whose collision volumes overlap.
- `connected_components: tuple[tuple[Placement[Element], ...], ...]` -- The placements grouped by connected component.

  Each group holds the parts joined to one another through couplings, with
  the groups and the parts within them in placement order. An empty model
  has no components.
- `connectors: frozenset[Connector]` -- Unoccupied connector points in this model's frame.

  A connector disappears here when it mates with another part, including across
  nested sub-model boundaries. Covering studs can therefore change the model's
  alignment box and how subsequent parts stack on it.
- `flattened_joints: tuple[Joint, ...]` -- All joint occurrences, with endpoint paths rooted in this model.

  A repeated sub-model contributes distinct records for each occurrence.
  Use these records as keys to ``posed`` when moving a nested joint.
- `flattened_placements: tuple[Placement[Element], ...]` -- Every element placement, flattened into this model's own frame.

  Flattening reaches through nested sub-models, so each leaf holds an
  :class:`Element`.
- `floating_placements: tuple[Placement[Element], ...]` -- Parts without a path to the ground through connectors or contact.

  The lowest physical extent defines the ground, as in
  `translate_to_ground`. The model's poses remain unchanged, and returned
  placements are the original leaves.

  Mated connectors transmit support in both directions. Surface contacts
  transmit it from the supporting part to the part resting on it, including
  on tiles, elevated ledges, and slopes. Sliding and tipping are not checked.
- `joints: tuple[Joint, ...]` -- Connections recorded in this model; nested records stay in their owner.

  Removing either endpoint, including a nested leaf, deletes its record.
- `names: Mapping[str, Placement]` -- The model's named placements, keyed by the name each was registered under.

  A live read-only view: names appear as parts are added.
- `num_connected_components: int` -- The number of connected components of the model.
- `placements: tuple[Placement, ...]` -- Every top-level placement in the model, in insertion order.

**Methods**

- `add(content: Element | LegoBuild, position: Position | tuple[float, float, float] = Position(0, 0, 0), rotation: Rotation = Rotation.DEG_0, anchor: Anchor = Anchor.FRONT_RIGHT, *, relative_to: NameRef | Placement | None = None, target_anchor: Anchor = Anchor.FRONT_RIGHT, name: str | None = None, index: int | None = None) -> Placement` -- Place content on the grid; return its placement.

  `position` is an absolute `(x, y, z)` or a delta from `relative_to` (a name,
  name path, or placement). `rotation` is the content's own rotation, not relative
  to the reference. Positions require integer x/y and z in whole plates.

  `anchor` selects the point on the content's rotated alignment footprint;
  `target_anchor` selects the reference point when using `relative_to`.
  The default is the front-right minimum corner. An even extent's center floors
  toward that corner: `Anchor.CENTER` on a 4x2 footprint is `(1, 0)` studs from it.

  `name` registers the result; `index` inserts instead of appending. Content is
  held by reference. A concrete reference is read in this model's frame, even
  if from another model or removed; it is not added automatically.

  Raises `ValueError` for off-grid positions, `KeyError` for missing names,
  and `IndexError` for an out-of-range insertion.
- `add_raw(content: Element | LegoBuild, pose: Pose = Pose(rotation=Mat3.IDENTITY, translation=Position(0, 0, 0)), *, name: str | None = None, index: int | None = None) -> Placement` -- Place content at an arbitrary pose without grid checks or re-anchoring.

  `pose` maps the content's local frame into this model. An element's origin is
  its alignment box's bottom-center; a sub-model retains its own frame.
  Content is shared by reference. `name` registers the placement and `index`
  inserts instead of appending. Invalid insertion indices raise `IndexError`.
- `check_motion(*, samples: int = 5, max_samples: int = 10000) -> MotionReport` -- Optionally check collisions, floating, and engagement across joint ranges.

  Samples the Cartesian product, including zero and both limits on every
  coordinate. Unannotated connections remain rigid, which can flag motions
  possible with additional flexibility. A clear report covers only the samples.
  Exceeding the sample budget or encountering a motion loop raises.
- `connect(content: Element | LegoBuild, connector: Connector | ConnectorType | str, to: Connector, *, mounting: Mounting | None = None, motion: MotionRange | None = None, target_rotation: Mat3 | Rotation | None = None, target_position: Position | tuple[float, float, float] | None = None, name: str | None = None, index: int | None = None) -> Placement` -- Place content by mating a local connector to a world target.

  ``target_rotation`` and ``target_position`` fit the pose; ``mounting`` then
  adds clocking, insertion, flip, or ball swing. Motion is relative to this pose.

  A target in this model records a static joint. Set ``motion`` to a
  ``MotionRange`` matching the joint's ``kind`` to enable movement.

  Both connectors must identify unique leaf occurrences. A geometric
  target outside this model may still position static content, but cannot
  declare motion. No placement or joint is recorded if validation fails.
- `copy() -> LegoBuild` -- A shallow copy holding the same placements under the same names.

  Placements and nested sub-models are shared. Build-step markers carry
  over. Adding to either outer model leaves the other alone; editing a
  shared sub-model affects both. Use :meth:`deepcopy` to isolate those edits.
- `deepcopy() -> LegoBuild` -- Copy this model and nested sub-models, isolating subsequent edits.

  Names, poses, and build steps are preserved. Repeated sub-models stay shared
  within the copy, but no mutable content is shared with the original.
- `extend(other: LegoBuild, position: Position | tuple[float, float, float] = Position(0, 0, 0), rotation: Rotation = Rotation.DEG_0, anchor: Anchor = Anchor.FRONT_RIGHT) -> tuple[Placement, ...]` -- Splice `other`'s current top-level placements into this model.

  The resulting geometry matches `add(other, position, rotation, anchor)`, but
  without a wrapper sub-model or its names. Returns the new placements in order.
  Later additions to `other` do not carry over; nested content remains shared.
  Raises `ValueError` for off-grid positions or cyclic nesting.
- `is_connected() -> bool` -- Whether the model has a single connected component.
- `is_valid() -> bool` -- Whether the model has no collisions or floating parts.
- `joint(child: Placement) -> Joint` -- The locally recorded joint that placed ``child`` using ``connect``.
- `list_elements() -> Counter[Element]` -- How many of each element -- part and color -- the model uses.
- `name_of(placement: Placement) -> str | None` -- The name ``placement`` was registered under, or ``None`` if unnamed.
- `named(name: NameRef) -> Placement` -- Look up a name or nested path such as `['tower', 'roof']`.

  Returns a placement in this model's frame, suitable for `relative_to` or `on`.
  That placement remains usable after removal, but looking up its removed name
  raises `KeyError`. An empty path or traversal through an element raises `ValueError`.
- `posed(positions: Mapping[Joint, JointCoordinates]) -> LegoBuild` -- A flat geometry snapshot at joint coordinates, leaving this build intact.

  Keys come from ``joints`` or ``flattened_joints``. Unspecified positions
  stay at zero. Static connections and attached rigid assemblies follow
  the moving parts. The snapshot has no joint records; evaluate every
  pose from the original build. Closed motion loops raise ``ValueError``.
- `remove(target: int | str | Placement) -> Placement` -- Remove and return a top-level placement by index, name, or identity.

  Negative indices count from the end. Repeated placements lose their first
  occurrence; the name is freed after the last. Build steps track the removal.
  Nested name paths are not accepted: edit the sub-model itself, which affects
  all models sharing it. Missing indices/names raise `IndexError`/`KeyError`;
  unknown placements raise `ValueError` and unsupported target types `TypeError`.
- `set_motion(joint: Joint | Placement, motion: MotionRange | None) -> Joint` -- Replace a local joint's range; ``None`` makes it static. Return the record.
- `stack(content: Element | LegoBuild, on: NameRef | Placement, offset: Position | tuple[float, float, float] = Position(0, 0, 0), rotation: Rotation = Rotation.DEG_0, anchor: Anchor = Anchor.FRONT_RIGHT, target_anchor: Anchor = Anchor.FRONT_RIGHT, *, name: str | None = None, index: int | None = None) -> Placement` -- Place content on top of `on` (a name, name path, or placement).

  The new part's alignment-box bottom rests at the reference's alignment-box top.
  `offset` shifts from there in studs/bricks and must be on the grid.
  Use `anchor=Anchor.CENTER, target_anchor=Anchor.CENTER` to center footprints;
  anchors, absolute rotation, shared content, naming, and insertion behave as in `add`.

  A concrete reference is read in this model's frame even if removed or from another
  model. Later changes to that reference do not move this placement.

### Constants

- `NameRef` = `str | Sequence[str]`

## Construction helpers

Fill simple boxes or wedges with valid parts. Large hollow structures should
be built from separate walls rather than filling their entire interior.

### Functions

#### `fill_box(corner_a: Position | tuple[float, float, float], corner_b: Position | tuple[float, float, float], color: Color = Color.WHITE) -> LegoBuild`

Return a model filling the box between two grid corners, in either order.

Uses bricks and plates without collisions; connected if taller than ``PLATE``.
Uses a single part when a brick or plate fits, including rotated sizes.
The interior is solid: use separate wall calls for large hollow structures,
and smaller calls for color patterns or details.

Raises ``ValueError`` for off-grid corners or zero extent on any axis.

#### `fill_inverted_slope(corner_a: Position | tuple[float, float, float], corner_b: Position | tuple[float, float, float], toward: Direction = Direction.FRONT, color: Color = Color.WHITE) -> LegoBuild`

Fill an inverted wedge inside the axis-aligned box spanned by two corners.

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

#### `fill_slope(corner_a: Position | tuple[float, float, float], corner_b: Position | tuple[float, float, float], toward: Direction = Direction.FRONT, color: Color = Color.WHITE) -> LegoBuild`

Fill a sloped wedge inside the axis-aligned box spanned by two corners.

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

## Recorded connections and sampled motion of LEGO assemblies

Mounting fixes the reference pose. A joint moves only after a ``MotionRange``
is assigned. ``posed`` evaluates coordinates without changing the build, and
``check_motion`` checks collisions, floating parts, and connector engagement over
the Cartesian product of sampled coordinates, including zero and both limits.
A clear report describes those samples, not a continuous guarantee. Angles are
degrees and sliding distances are studs.

Rigid groups follow static recorded connections and connector matings in the
reference pose. Sub-model nesting is organizational: disconnected parts do not
move together merely because they share a sub-model. This optional check can flag
motions that would be possible if other, unannotated connections could move.

```python
import bricklayer as bl

model = bl.LegoBuild()
base = model.add(bl.Element("3680", bl.Color.WHITE))
top = model.connect(
    bl.Element("3679", bl.Color.RED), "turntable_pin",
    to=base.find_connector("turntable_socket"),
    mounting=bl.Mounting(angle=20),
    motion=bl.MotionRange(bl.Revolute(-45), bl.Revolute(45)),
)
preview = model.posed({model.joint(top): bl.Revolute(30)})
report = model.check_motion(samples=5)
assert report.passed
```

### Classes

#### class `MotionRange`

`MotionRange(lower: JointCoordinates, upper: JointCoordinates) -> None`

Inclusive lower/upper coordinates of one kind, each containing zero.

For example ``MotionRange(Revolute(-45), Revolute(90))`` or
``MotionRange(Prismatic(-0.5), Prismatic(0.5))``. Multi-coordinate ranges
describe every combination, not a diagonal path between the endpoints.
Equal bounds at zero lock that coordinate.

**Properties**

- `lower: JointCoordinates`
- `upper: JointCoordinates`

#### class `Joint`

A connection between two occurrences; ``motion=None`` holds it static.

``kind`` describes allowed motion; ``motion`` declares its range. Use
``model.set_motion`` to change it and ``model.check_motion`` to validate it.

**Properties**

- `kind: JointKind`
- `motion: MotionRange | None`

#### class `MotionReport`

Collision, support, and engagement results at all requested samples.

**Properties**

- `collisions: tuple[MotionCollision, ...]`
- `disconnections: tuple[MotionDisconnection, ...]`
- `floating: tuple[MotionFloating, ...]`
- `passed: bool` -- Every sample is collision-free, supported, and retains its connections.
- `samples_checked: int`

#### class `MotionCollision`

An intersecting pair of reference leaves and the sampled joint positions.

**Properties**

- `placements: tuple[Placement, Placement]`
- `positions: tuple[tuple[Joint, JointCoordinates], ...]`

#### class `MotionDisconnection`

A recorded connection that no longer mates at a sampled configuration.

**Properties**

- `joint: Joint`
- `positions: tuple[tuple[Joint, JointCoordinates], ...]`

#### class `MotionFloating`

Unsupported reference leaves and the sampled joint positions.

**Properties**

- `placements: tuple[Placement, ...]`
- `positions: tuple[tuple[Joint, JointCoordinates], ...]`

## Model transformations

These functions return new objects, leaving their inputs intact.
Use `translate_to_ground(model)` to put the lowest physical extent on z=0.

### Functions

#### `translate(model: LegoBuild, delta: Position | tuple[float, float, float]) -> LegoBuild`

Translate ``model`` by ``(dx, dy, dz)`` -- x/y in studs, z in bricks. Returns a new :class:`LegoBuild`.

#### `translate_to_ground(model: LegoBuild) -> LegoBuild`

Translate ``model`` so its lowest volume rests on z = 0. Returns a new :class:`LegoBuild`.

This can help you ground a floating model.

#### `flatten(model: LegoBuild) -> LegoBuild`

Return a new model containing only leaf element placements.

Preserves names of existing top-level leaves; drops build-step markers.

#### `mirror(geometry: LegoBuild | Placement | Element, axis: Axis, plane: Scalar = 0) -> LegoBuild | Placement | Element`

Reflect ``geometry`` across the plane ``plane`` on ``axis`` -- ``x =
plane`` for ``Axis.X`` (left/right), ``y = plane`` for ``Axis.Y``
(front/back). ``plane`` is in studs. Returns a new object of the same kind.

Models and placements reflect positions and orientations, keeping names,
colors, grounding, and shared sub-models. To mirror a model where it stands,
use its alignment-box center on ``axis`` as the plane.

Handed elements swap for their opposite-handed part; for a standalone
element, ``axis`` and ``plane`` are ignored. Parts without a counterpart,
or with differently measured counterparts, retain their original shape.
