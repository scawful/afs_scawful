#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def add_afs_scawful_src() -> None:
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[2] / "src" / "lab" / "afs-scawful" / "src",
        script_path.parents[2] / "src" / "afs-scawful" / "src",
        script_path.parents[2] / "src",
        Path("D:/src/lab/afs-scawful/src"),
        Path("D:/src/afs-scawful/src"),
    ]
    for candidate in candidates:
        if (candidate / "afs_scawful").exists():
            path_str = str(candidate)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)
            return


add_afs_scawful_src()

from afs_scawful.windows.hostd import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
