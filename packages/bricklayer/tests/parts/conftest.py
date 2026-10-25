import pytest

from bricklayer.ldraw import partdata
from bricklayer.parts import catalog


@pytest.fixture
def patch_shape_overrides(monkeypatch):
    """Swap the hand-authored shape overrides for the ones given.

    Also drops what was already derived with the real ones: ``_shape_of``
    caches by id, so a stale answer would outlive the swap.
    """

    def _fn(overrides: dict[str, dict]) -> None:
        monkeypatch.setattr(partdata, "shape_override", overrides.get)
        catalog._shape_of.cache_clear()

    yield _fn
    catalog._shape_of.cache_clear()
