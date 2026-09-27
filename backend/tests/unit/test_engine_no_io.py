"""Guards DEV-REQ-002: pachapp_engine must stay pure (no I/O)."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_MODULES = {"sqlite3", "sqlmodel", "httpx", "sqlalchemy"}


def _iter_engine_source_files() -> list[Path]:
    import pachapp_engine

    package_dir = Path(pachapp_engine.__file__).parent
    return sorted(package_dir.rglob("*.py"))


def _imported_module_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_pachapp_engine_has_no_io_imports() -> None:
    source_files = _iter_engine_source_files()
    assert source_files, "expected at least pachapp_engine/__init__.py"

    for path in source_files:
        offending = _imported_module_roots(path.read_text()) & FORBIDDEN_MODULES
        assert not offending, f"{path} imports forbidden I/O module(s): {offending}"
