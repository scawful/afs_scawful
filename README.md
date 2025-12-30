# AFS Scawful Plugin

Research-only. Not a product.

Scope: Scawful-specific plugin utilities, generators, and validators.

Provenance: avoid employer/internal sources; skip unclear origins.

Docs:
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- `docs/REPO_FACTS.json`
- `docs/TRAINING_ROADMAP.md`
- `docs/TRAINING_PLAN.md`
- `docs/PDF_WORKFLOW.md`

Quickstart:
- `python -m afs_scawful datasets index`
- `python -m afs_scawful resources index`
- `python -m afs_scawful validators list`
- `python -m afs_scawful generators doc-sections --output ~/src/training/index/doc_sections.jsonl`
- `python -m afs_scawful research catalog`
- `python -m afs_scawful research list`

Mounts (AFS Studio):
- Create `mounts.json` in `~/.config/afs/afs_scawful/` or `~/.config/afs/plugins/afs_scawful/config/`
- Optional override: `AFS_SCAWFUL_MOUNTS=/path/to/mounts.json`
- Mount entries are user-specific; keep this file out of version control.

Example `mounts.json`:
```json
{
  "mounts": [
    { "name": "Projects", "path": "~/projects" },
    { "name": "Training", "path": "~/Mounts/windows-training" },
    { "name": "Reference", "path": "~/docs/reference" }
  ]
}
```

Training monitor (AFS Studio):
- Use `training_monitor` in `mounts.json` or a separate `training_monitor.json` in the same config dirs.
- Optional override: `AFS_TRAINING_MONITOR_CONFIG=/path/to/training_monitor.json`

Example `training_monitor` block:
```json
{
  "training_monitor": {
    "windows_mount_path": "~/Mounts/windows-training",
    "windows_training_dir": "D:/afs_training"
  }
}
```
