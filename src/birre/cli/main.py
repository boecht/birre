"""CLI entry point wrapper.

The :func:`main` function simply proxies to the Typer application
exported by :mod:`birre.cli.app`. Once the refactor finishes the
implementation will live here directly.
"""

from __future__ import annotations

from birre.cli.app import main as _legacy_main


def main(argv: list[str] | None = None) -> None:
    """Invoke the legacy CLI entry point.

    Parameters
    ----------
    argv:
        Optional list of arguments to pass to Typer. When ``None`` the
        process arguments are used.
    """

    _legacy_main(argv)


__all__ = ["main"]
