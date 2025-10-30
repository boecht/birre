"""Package data helpers for BiRRe."""

from collections.abc import Iterator
from importlib import resources as _resources
from importlib.abc import Traversable
from typing import cast

__all__ = ["iter_data_files"]


def iter_data_files(pattern: str) -> Iterator[str]:
    """Yield resource paths within the package matching a suffix pattern."""
    root = _resources.files(__name__)
    # Cast needed because Traversable protocol doesn't declare rglob in the stub
    for entry in cast("type[Traversable]", root).rglob(pattern):  # type: ignore[attr-defined]
        if entry.is_file():
            yield str(entry)
