# Storage Layout and Cache Policy

Goal: keep macOS as the control plane (code + indexes) and move heavy artifacts
to Windows drives to avoid filling the 1TB Mac SSD.

## Recommended Roots

Primary (Windows D: via mount):
- `~/Mounts/mm-d/afs_training` -> `D:\afs_training`

Overflow / backup:
- `~/Mounts/mm-e/afs_training_backup` -> `E:\afs_training_backup`

## SCP Fallback (When Mounts Are Unstable)

Use direct SSH copy to the Windows host (preferred when SSHFS is flaky):

```bash
scp /path/to/artifact.tar.gz mm-lan:/D:/afs_training/models/
scp /path/to/logs/*.log mm-lan:/D:/afs_training/logs/
```

## Suggested Directory Tree (Windows)

```
D:\afs_training\
  raw\                # raw scans, unprocessed sources
  ocr\                # OCR outputs (PDF + text)
  datasets\           # curated datasets (train/val/test)
  index\              # dataset_registry.json, resource_index.json
  models\             # model weights, adapters, exports
  checkpoints\        # long-running training checkpoints
  runs\               # training logs + metadata
  exports\            # GGUF/MLX exports
  cache\              # HF/transformers/torch caches
```

## Config: training_paths.toml

Create `~/.config/afs/afs_scawful/training_paths.toml`:

```toml
[paths]
training_root = "~/Mounts/mm-d/afs_training"
datasets = "~/Mounts/mm-d/afs_training/datasets"
index_root = "~/Mounts/mm-d/afs_training/index"
```

This keeps AFS Scawful indexing pointed at the Windows mount.

## Optional: Resource Index Scope

Create `~/.config/afs/afs_scawful/training_resources.toml` to keep the resource
index fast and focused:

```toml
[resource_discovery]
resource_roots = [
  "~/Mounts/mm-d/afs_training/datasets",
  "~/Mounts/mm-d/afs_training/ocr"
]
search_patterns = ["**/*.jsonl", "**/*.md", "**/*.txt", "**/*.pdf"]
exclude_patterns = ["archive", "tmp"]
index_path = "~/Mounts/mm-d/afs_training/index/resource_index.json"
```

## Cache Environment (Mac)

Put large caches on Windows to avoid filling the Mac SSD:

```bash
export HF_HOME=~/Mounts/mm-d/afs_training/cache/huggingface
export TRANSFORMERS_CACHE=$HF_HOME
export TORCH_HOME=~/Mounts/mm-d/afs_training/cache/torch
export XDG_CACHE_HOME=~/Mounts/mm-d/afs_training/cache
export OLLAMA_MODELS=~/Mounts/mm-d/afs_training/models/ollama
```

## What Stays on Mac

- Source code (`~/src`)
- Small indexes (`~/src/training/index` if desired)
- Docs and configs

## What Moves to Windows

- Large datasets and raw scans
- Model weights, adapters, checkpoints
- HF/transformers/torch caches

## Backup Notes

- Use `mm-e` for periodic backups of `D:\afs_training\models` and `datasets`.
- Keep backups off the Mac to preserve local disk space.
