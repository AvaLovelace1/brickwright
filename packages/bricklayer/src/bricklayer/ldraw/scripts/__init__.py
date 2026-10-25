"""Scripts that regenerate the committed LDraw data files.

The five ``extract_part_*`` scripts each write a data file committed alongside the
package, so no library is needed at runtime. Geometry and taxonomy come from the
official LDraw library (via ``--ldraw`` or ``$LDRAW_LIBRARY_PATH``); connectors and
collision meshes come from BrickNet, resolved against that same library; popularity
comes from Rebrickable's catalogue downloads and needs neither. ``run_all`` drives
all five.
"""
