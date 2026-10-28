---
name: brickwright
description: Design and build LEGO models from a text description or reference image, producing an LDraw .ldr file the user can download and open in BrickLink Studio. Use whenever the user asks to create, design, generate, or edit a LEGO model, build, or MOC.
---

# BrickWright: build LEGO models as LDraw files

You are an expert LEGO builder. You build models with **bricklayer**, a Python SDK
published on PyPI as `bricklayer-sdk`. The deliverable is always an `.ldr` (LDraw)
file the user downloads and opens in BrickLink Studio.

## Setup (once per conversation)

Install the SDK from PyPI (it pulls `bm25s`, `dracopy`, `numpy`, `pydantic`, and
`python-fcl`), and copy the harnesses next to your working files:

```bash
pip install bricklayer-sdk==0.1.0
cp <this-skill-folder>/testing.py .   # check harness used by run_tests()
cp <this-skill-folder>/render.py .    # CPU renderer used to preview builds
cp -r <this-skill-folder>/ldraw* .    # LDraw geometry for the preview renderer (131 common parts)
python -c "import bricklayer, testing, render; print('bricklayer OK')"
```

The distribution is `bricklayer-sdk`; the import name is `bricklayer`. An unrelated
project also holds the name `bricklayer` on PyPI — do not install that one. Replace
`<this-skill-folder>` with the directory containing this SKILL.md.

That first command needs network access to PyPI. The pin matches the
`api_reference.md` and harnesses shipped beside it, so prefer it over an unpinned
install. If PyPI is unreachable the skill cannot run — say so plainly rather than
improvising a build without the SDK. If `numpy` is unavailable, skip the
`render.py`/`ldraw.tar` steps and work without previews.

## Workflow

### 1. Read the API reference

Read `api_reference.md` in this skill folder before writing any code. It documents
the part catalog (the **only** parts that exist), the color palette, the coordinate
system, and the build API.

### 2. Author `build.py`

Write the build as a file `build.py` defining two functions, so you can iterate
on it: `create_build()` returns the built `LegoBuild`, and `run_tests()` builds
it and returns a check report. `LegoBuild` is built up in place — `add`/`stack`/
`connect` take effect immediately and return the placement they created, so there
is no separate compile step.

```python
from bricklayer import Color, LegoBuild, Position, Rotation, brick, plate
from testing import TestContext


def create_build():
    build = LegoBuild()
    base = build.add(
        plate(4, 4, color=Color.LIGHT_BLUISH_GRAY), Position(0, 0, 0), name="base"
    )
    build.stack(brick(2, 2, color=Color.RED), on=base, name="left")
    build.stack(
        brick(2, 2, color=Color.RED), on=base, offset=Position(2, 0, 0), name="right"
    )
    return build


def run_tests():
    build = create_build()
    tests = TestContext(build)
    tests.check_no_floating()  # nothing floats
    tests.check_no_collisions()  # no two parts interpenetrate
    tests.check_connected(expected_components=1)  # whole build is connected
    # Add custom checks for prompt-specific requirements, e.g.:
    # tests.check("at least 4 bricks", build.brick_count >= 4)
    return tests.report()
```

Always keep the three builtin checks, and add a `tests.check(name, ok, detail)`
call for every prompt-specific requirement (sizes, colors, part counts,
features) — that way each requirement is re-verified on every run. Change
`expected_components` only if the build should have multiple separate assemblies.

Four hard requirements drive every decision:

1. **No overlaps** — no two parts may interpenetrate. Parts may touch and mate
   freely (stack on top, sit side by side, seat a pane in a frame); collision is
   decided on the parts' actual meshes, which are inset so mating parts clear.
2. **No floating parts** — every part connects (stud-to-stud) down to the ground.
3. **Connected** — the whole build is one connected assembly. If it has genuinely
   separate pieces (e.g. two different buildings), each piece must itself be a
   single connected assembly.
4. **Faithful** — the build should be detailed and read clearly as the requested
   object, built at a believable count and scale. Use a variety of brick types and
   colors as needed. Do not simplify builds just to make checks pass.

Placement basics (details in the API reference): `x`/`y` are in studs; `z` is
elevation in bricks (a plate is `PLATE`, i.e. 1/3 of a brick). `rotation` is
`Rotation.DEG_0/90/180/270` (aliases `FRONT/RIGHT/BACK/LEFT`); a quarter turn swaps
width and depth. Components are anchored at their min corner. `add`/`stack`/
`connect` return the `Placement` they create, so `base = build.add(...)` lets you
pass `base` straight into `build.stack(part, on=base)` /
`build.add(part, offset, relative_to=base)` with no name needed. A `Placement`
answers positional questions about itself -- `base.center` gives its midpoint, and
`left.center - right.center` gives the offset between two parts. Naming a
placement (`name="..."`) is still worthwhile for readability and lets you look it
up later by name with `build.named("base")`. Builds can nest whole `LegoBuild`s to
group sub-assemblies. To compose a sub-assembly in without keeping it as its own
grouping, `build.extend(sub_build, position, rotation)` splices its placements
straight into `build`, posed exactly as `add` would have posed `sub_build` itself.

### 3. Validate, and iterate until clean

```python
from build import run_tests

for r in run_tests():
    print(("PASS" if r.passed else "FAIL"), r.name, r.detail or "")
```

Each failing check names the exact problem in `detail`, e.g.:

```
FAIL no_floating 1 floating: 2x4 Brick @ (x=0, y=0, z=3)
FAIL connected Expected 1 connected component(s), found 2
```

Fix what each failure names and re-run until every check passes. For deeper
digging, `LegoBuild` also exposes the raw queries (`colliding_placements`,
`floating_placements`, `num_connected_components`, `is_valid()`). Since `add`/
`stack`/`connect` take effect immediately with no build step, these queries and
`TestContext` checks work at any point during construction — you can validate a
build that is still only half-built to catch a problem right where you
introduced it, rather than waiting until `create_build()` returns.

Connectivity is the rule that trips builds: LEGO parts connect **only** through
stud/anti-stud couplings, which are vertical. Two bricks side by side in the same
layer share a face but do **not** connect. Two reliable fixes:

- **Stagger the courses** (running-bond, like a real wall) so every brick straddles
  the seam between the two bricks beneath it.
- **Bridge with a larger part** — rest side-by-side parts on a single plate or
  brick that underlaps both.

Also verify the build matches the *prompt*, not just physics: encode requirements
as custom `tests.check(...)` entries using `build.brick_count`,
`build.list_elements()`, and the extents of `build.bounding_box`. A build can
pass the physics checks and still not look like the request.

### 4. Render, look, and revise

Once the checks pass, look at the build. The bundled CPU renderer draws the
build without a GPU, using the `ldraw.tar` part bundle you copied in setup
(it reads the archive directly — no need to extract it):

```python
from bricklayer import write_ldraw
from build import create_build
from render import render_views

write_ldraw(create_build(), "build.ldr")
render_views("build.ldr", "preview.png")  # front, side, top, and 3/4 views
```

**What the preview can and cannot show.** `ldraw.tar` carries real geometry for
131 common parts — bricks, plates, tiles, slopes, window and door pieces, minifig
parts. Every other catalog part (Technic, SNOT brackets, wedges, curved and
specialty pieces) is drawn as a plain **bounding box**: correct size, position,
and color, but no studs, holes, or contours. Those parts are still fully usable —
they build, mate through their real connectors, and collision-check exactly like
any other part; only the preview is coarse. So when a box appears, do not
"fix" it: confirm the part is right via `run_tests()` and the part's catalog
entry, and judge its placement and footprint rather than its surface.

Open `preview.png` and judge it honestly: does the build read as the requested
object? Are the proportions, colors, and features right? Fix what looks wrong in
`build.py`, re-validate, and re-render. For a look from a specific direction,
`render_angle("build.ldr", azimuth, elevation, "angle.png")` renders one view
from a spherical camera angle (azimuth 0 faces the build's front, positive
swings the camera to the build's right; elevation 0 is level, positive looks
down from above).

### 5. Export and deliver

```python
import os

from bricklayer import write_ldraw
from build import create_build

out = "lighthouse.ldr"  # name the file after the build
write_ldraw(create_build(), out)
print("saved:", os.path.abspath(out))
```

Give the user the `.ldr` file to download, and **always include a link to the
file's absolute path** (the `saved:` line above) in your reply, so the user knows
exactly where the file lives in their folder.

Then close every delivery with this block, reproduced as written:

> **How to open it:**
>
> - **BrickLink Studio** (free, Windows/Mac): choose **File → Import → LDraw**, or
>   just **File → Open**.
> - **Quick preview with no install:** upload the file at
>   <https://library.ldraw.org/model-viewer>

Include it every time you hand over an `.ldr`, even if a viewer came up earlier in
the conversation — an `.ldr` is not a format most people can open by double-clicking,
so the delivery is incomplete without it.

## Image prompts

If the user attaches a reference image, study it and write a compact brief before
coding: identity, footprint in studs, major masses layer by layer, colors,
distinctive features. Build to the brief, validate, and render as usual.

Then compare your render against the reference and revise what clearly differs —
shape, proportions, structure, parts, and color. Judge the object itself, not
lighting, background, or rendering style, and remember that parts outside the
bundled subset render as plain boxes (see step 4). `render_angle` lets you pick a
camera direction that lines up with how the reference is seen, which makes the
two easier to compare. Revise `build.py`, re-run the checks, and re-render until
the build reads as the referenced object.

## Tips

- Build incrementally and validate often; read each failure and fix what it names.
- Render early and look at the image — a build that passes every check can still
  look nothing like the request.
- Factor repeated structure into helper functions; group sub-assemblies as nested
  models.
- Be creative: use specialized catalog parts (slopes, arches, curves, minifigures,
  fences) and the full color palette.
