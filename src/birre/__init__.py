"""Top-level BiRRe package API."""

from birre.application.server import (
    INSTRUCTIONS_MAP,
    _resolve_tls_verification,
    create_birre_server,
)

__version__ = "4.0.0"

__all__ = [
    "create_birre_server",
    "_resolve_tls_verification",
    "INSTRUCTIONS_MAP",
    "__version__",
]
