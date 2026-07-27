from __future__ import annotations

import ast
from pathlib import Path

from conftest import CORE_OWNED_TESTS


TEST_ROOT = Path(__file__).resolve().parent
ALLOWED_CORE_IMPORTS = {"afs.history"}


def is_disallowed_core_import(module: str) -> bool:
    return module == "afs" or (
        module.startswith("afs.") and module not in ALLOWED_CORE_IMPORTS
    )


def test_core_import_guard_covers_root_and_domain_forms() -> None:
    assert is_disallowed_core_import("afs")
    assert is_disallowed_core_import("afs.training")
    assert not is_disallowed_core_import("afs.history")
    assert not is_disallowed_core_import("afs_scawful.training")


def test_active_plugin_tests_do_not_import_copied_core_domains() -> None:
    violations: list[str] = []
    ignored = {Path(name) for name in CORE_OWNED_TESTS}
    assert all((TEST_ROOT / path).is_file() for path in ignored)
    for path in sorted(TEST_ROOT.rglob("test_*.py")):
        relative = path.relative_to(TEST_ROOT)
        if relative in ignored:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if is_disallowed_core_import(module):
                    violations.append(f"{relative}:{node.lineno} {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "afs" or alias.name.startswith("afs."):
                        violations.append(
                            f"{relative}:{node.lineno} {alias.name}"
                        )

    assert violations == []
