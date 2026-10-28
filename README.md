# BrickWright

Design and build LEGO® models from a text description or a reference image, and get back an
LDraw `.ldr` file you can open in BrickLink Studio and build for real.

BrickWright turns a prompt like "a red lighthouse on a rocky base" into an actual brick model.
It writes Python against the [BrickLayer](https://pypi.org/project/bricklayer-sdk/) SDK, assembles
the build part by part, and checks it against real physical constraints before handing it over:

- **No interpenetrating parts** — collisions are decided on the parts' actual meshes, not bounding boxes.
- **Nothing floating** — every part connects down to the ground.
- **One connected assembly** — the model holds together as a single piece.

It previews the result with a built-in CPU renderer, so it can look at what it built, spot what is
wrong, and revise before delivering. No GPU and no API key are needed: the skill runs entirely in
the host's code-execution sandbox.

The catalog covers over 21,000 LDraw parts — bricks, plates, tiles, slopes, windows, doors,
minifigures, Technic beams and pins, SNOT brackets — in the full LEGO color palette, with real
connector data so parts mate the way they do in life.

## What you get

An `.ldr` file, plus instructions for opening it. BrickLink Studio (free, Windows and Mac) imports
it directly, and the LDraw model viewer previews it in a browser with nothing to install.

## Requirements

The skill installs `bricklayer-sdk` from PyPI on first use, so the sandbox needs network access to
the package registry.

## Credits

BrickWright is a research project from Carnegie Mellon University, Stanford University, and
independent collaborators. Part geometry comes from the [LDraw](https://ldraw.org/) parts library,
used under the CC BY 2.0 license, with set-popularity data from
[Rebrickable](https://rebrickable.com/downloads/).

LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize, or endorse this project.
