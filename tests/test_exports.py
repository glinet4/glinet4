"""Guard glinet4.__all__ against import/export drift.

Two invariants:

1. ``__all__`` must exactly match the names ``glinet4/__init__.py`` imports
   (no stray export, nothing imported and silently left out).
2. Every public ``TypedDict`` defined in ``glinet4._types`` (public = no
   leading underscore) must be exported, so consumers can import response
   shapes without reaching into the private ``_types`` module.
"""

import ast
import typing
from pathlib import Path

import glinet4
from glinet4 import _types

INIT_PATH = Path(glinet4.__file__)


def _names_imported_by_init() -> set[str]:
    """Return every name bound by an ``from .x import ...`` in __init__.py."""
    tree = ast.parse(INIT_PATH.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _public_typeddict_names() -> set[str]:
    """Return public (non-underscore) TypedDict class names in glinet4._types."""
    return {
        name
        for name, obj in vars(_types).items()
        if not name.startswith("_") and isinstance(obj, type) and typing.is_typeddict(obj)
    }


def test_all_matches_names_imported_by_init():
    assert set(glinet4.__all__) == _names_imported_by_init()


def test_every_public_typeddict_is_exported():
    missing = _public_typeddict_names() - set(glinet4.__all__)
    assert not missing, f"public TypedDicts missing from glinet4.__all__: {sorted(missing)}"
