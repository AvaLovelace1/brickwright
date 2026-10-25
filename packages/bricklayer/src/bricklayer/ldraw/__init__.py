"""LDraw part data: geometry, connectivity, meshes, and the coordinate frame.

Nothing here imports :mod:`bricklayer.modeling`, :mod:`bricklayer.parts`, or
:mod:`bricklayer.construction`. Turning a model into LDraw text, and reading one
back, is :mod:`bricklayer.io`.
"""

from .partdata import get_connector_type

__all__ = ["get_connector_type"]
