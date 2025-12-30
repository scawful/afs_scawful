# AFS Scawful Plugin

Research-only. Not a product.

Scope: Scawful-specific plugin utilities, generators, and validators.

Provenance: avoid employer/internal sources; skip unclear origins.

Docs:
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- `docs/REPO_FACTS.json`

Quickstart:
- `python -m afs_scawful datasets index`
- `python -m afs_scawful resources index`

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
