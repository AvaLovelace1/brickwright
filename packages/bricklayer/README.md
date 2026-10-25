# BrickLayer

**BrickLayer** is an SDK for programmatically creating and validating LEGO® builds.
Using only Python code, you can assemble models from real catalog parts, query them for structural problems (collisions,
floating parts, disconnected pieces), and export them directly to [LDraw](https://www.ldraw.org/).

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
uv run python -m bricklayer
```

---

*LEGO® is a trademark of the LEGO Group, which does not sponsor, authorize, or endorse this project.*
