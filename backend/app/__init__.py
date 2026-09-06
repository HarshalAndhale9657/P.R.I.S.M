"""HTTP layer. ``create_app`` is resolved lazily so that importing ``app.settings``
or ``app.schemas`` from the worker/pipeline layers does not drag in the factory —
which imports the worker, which imports this package: the circular import that
ADR-0029 removed. ``from app import create_app`` and ``app.create_app()`` still work."""
from __future__ import annotations

from .settings import APP_VERSION, Settings, get_settings  # settings has no app-internal imports: safe eagerly

__all__ = ["create_app", "APP_VERSION", "Settings", "get_settings"]


def __getattr__(name: str):
    if name == "create_app":
        from .factory import create_app
        return create_app
    raise AttributeError(f"module 'app' has no attribute {name!r}")
