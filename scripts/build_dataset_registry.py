"""Build the dataset registry for AFS Scawful."""

from __future__ import annotations

from afs_scawful.registry import index_datasets


def main() -> int:
    path = index_datasets()
    print(f"dataset_registry: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
