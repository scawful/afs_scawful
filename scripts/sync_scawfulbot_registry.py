#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    src_root_str = str(src_root)
    if src_root_str not in sys.path:
        sys.path.insert(0, src_root_str)


def main() -> int:
    _ensure_src_on_path()
    from afs_scawful.scawfulbot_registry_sync import main as sync_main

    return sync_main()


if __name__ == "__main__":
    raise SystemExit(main())
