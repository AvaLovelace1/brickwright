# BrickLayer

**BrickLayer** is an SDK for programmatically creating and validating LEGO® builds.
Using only Python code, you can assemble models from real catalog parts, query them for structural problems (collisions,
floating parts, disconnected pieces), and export them directly to [LDraw](https://www.ldraw.org/).

## Installation

```sh
pip install bricklayer-sdk
```

## Quickstart

```python
import bricklayer as bl

model = bl.LegoBuild()
base = model.add(bl.plate(4, 4, color=bl.Color.GREEN), (0, 0, 0), name="base")
model.stack(bl.brick(2, 2, color=bl.Color.RED), on=base)

assert model.is_valid()  # no collisions, nothing floating
bl.write_ldraw(model, "tower.ldr")  # open in any LDraw viewer
```

## API reference

For the full API reference, see `bricklayer.api_reference()` or run the following command:

```sh
python -m bricklayer
```

---

*Bundled part data derive from the [LDraw.org Parts Library](https://library.ldraw.org/) (CC BY 2.0/4.0),
[BrickNet](https://github.com/kulits/BrickNet) (MIT), and [Rebrickable](https://rebrickable.com/downloads/); see
[NOTICE](https://github.com/AvaLovelace1/brickwright/blob/main/packages/bricklayer/NOTICE).*

*LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize, or endorse this project.*
