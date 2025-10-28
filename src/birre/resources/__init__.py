"""Package data helpers for BiRRe."""

from collections.abc import Iterator
from importlib import resources as _resources

__all__ = ["iter_data_files"]


def iter_data_files(pattern: str) -> Iterator[str]:
    """Yield resource paths within the package matching a suffix pattern."""
    root = _resources.files(__name__)
    for entry in root.rglob(pattern):
        if entry.is_file():
            yield str(entry)
