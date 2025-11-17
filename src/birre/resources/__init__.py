"""Package data helpers for BiRRe."""

from collections.abc import Iterator
from importlib import resources as _resources

try:
    from importlib.resources.abc import Traversable
except ImportError:  # pragma: no cover - fallback for older interpreters
    from importlib.abc import Traversable
from typing import Protocol, cast

__all__ = ["iter_data_files"]


def iter_data_files(pattern: str) -> Iterator[str]:
    """Yield resource paths within the package matching a suffix pattern."""
    root = _resources.files(__name__)
    rglobber = cast(_SupportsRGlob, root)
    for entry in rglobber.rglob(pattern):
        if entry.is_file():
            yield str(entry)


class _SupportsRGlob(Protocol):
    def rglob(self, pattern: str) -> Iterator[Traversable]: ...
