"""Rebuild the resource index for AFS Scawful."""

from __future__ import annotations

from afs_scawful.resource_index import ResourceIndexer


def main() -> int:
    indexer = ResourceIndexer()
    result = indexer.build_index()
    path = indexer.write_index(result)
    print(f"resource_index: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
