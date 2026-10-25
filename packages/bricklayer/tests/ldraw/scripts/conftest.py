"""Shared fixtures for the LDraw extraction-script tests."""

import json
import lzma
import os
from pathlib import Path

import pytest

from bricklayer.ldraw.scripts.library import Library

#: The three env vars the integration tests need: the official LDraw library,
#: BrickNet's inset collision meshes, and BrickNet's own data directory.
_ENV_VARS = ("LDRAW_LIBRARY_PATH", "BRICKNET_MESHES", "BRICKNET_DATA")


@pytest.fixture
def bricknet_data(tmp_path):
    """Original labels for two parts and one rigid alias."""
    root = tmp_path / "bricknet"
    root.mkdir()
    labels = {
        "3001.dat": {
            "stud": {"stud": [[-30, 0, -10], [30, 0, 10]]},
            "hole": {"hole": [[-30, 24, -10, 0.0, 0.0]]},
        },
        "30124b.dat": {
            "hinge": {"5": {"in": [[0, 8, 0.7, 0.0, 90.0, 0]]}},
            "hole": {"tube": [[0, 0, 0]]},
        },
    }
    aliases = {
        "rows": [
            {
                "src": "2446",
                "dst": "30124b",
                "final_matrix_3x4": [0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1],
            }
        ]
    }
    for name, data in [("labels", labels), ("part_aliases", aliases)]:
        (root / f"{name}.json.xz").write_bytes(lzma.compress(json.dumps(data).encode()))
    return root


@pytest.fixture
def ldraw_library():
    """The real LDraw library, skipped unless all three BrickNet/LDraw env vars
    are set -- the same three :func:`~bricklayer.ldraw.scripts.library.selected_part_ids`
    reads."""
    missing = [name for name in _ENV_VARS if not os.environ.get(name)]
    if missing:
        pytest.skip(f"requires ${', $'.join(missing)}")
    return Library(Path(os.environ["LDRAW_LIBRARY_PATH"]))


@pytest.fixture
def ldraw_root(tmp_path):
    """A fake-library factory: ``ldraw_root({"parts/3005.dat": "..."}) -> root``.

    Always creates ``parts/`` so the root passes :meth:`Library.find`'s check.
    """

    def make(files: dict[str, str | bytes]):
        (tmp_path / "parts").mkdir(exist_ok=True)
        for rel, content in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content)
        return tmp_path

    return make
