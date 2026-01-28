#!/usr/bin/env bash
set -euo pipefail

ROOT="${AFS_TRAINING_ROOT:-$HOME/src/training}"
DATASETS_ROOT="${AFS_DATASETS_ROOT:-$ROOT/datasets}"
INDEX_ROOT="${AFS_INDEX_ROOT:-$ROOT/index}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -m afs_scawful datasets index --root "$DATASETS_ROOT" --output "$INDEX_ROOT/dataset_registry.json"
"$PYTHON_BIN" -m afs_scawful resources index --output "$INDEX_ROOT/resource_index.json"

echo "dataset_registry: $INDEX_ROOT/dataset_registry.json"
echo "resource_index: $INDEX_ROOT/resource_index.json"
