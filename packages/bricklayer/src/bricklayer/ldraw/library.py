"""Optional official-library data for importing colors and rigid part aliases."""

from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path

from ..geometry import Pose
from .conversion import pose_from_type1


@dataclass
class ImportLibrary:
    root: Path
    _redirects: dict[str, tuple[str, Pose] | None] = field(default_factory=dict)

    def redirect(self, part_id: str) -> tuple[str, Pose] | None:
        """One rigid, color-inheriting alias; never expand arbitrary geometry."""
        if part_id not in self._redirects:
            self._redirects[part_id] = self._read_redirect(part_id)
        return self._redirects[part_id]

    def _read_redirect(self, part_id: str) -> tuple[str, Pose] | None:
        if not part_id or Path(part_id).name != part_id or "\\" in part_id:
            return None
        parts = (self.root / "parts").resolve()
        path = parts / f"{part_id}.dat"
        if not path.is_file() or not path.resolve().is_relative_to(parts):
            return None
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines or not lines[0].startswith(("0 ~Moved to ", "0 =")):
            return None
        geometry = [
            line.split(maxsplit=14)
            for line in lines
            if line.strip() and line.split()[0] != "0"
        ]
        if len(geometry) != 1:
            return None
        fields = geometry[0]
        if len(fields) != 15 or fields[:2] != ["1", "16"]:
            return None
        target = fields[14].lower()
        if not target.endswith(".dat") or Path(target).name != target or "\\" in target:
            return None
        try:
            numbers = [float(v) for v in fields[2:14]]
            if not all(isfinite(v) for v in numbers):
                return None
            pose = pose_from_type1(numbers)
        except ValueError:
            return None
        return target.removesuffix(".dat"), pose
