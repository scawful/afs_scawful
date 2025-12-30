# PDF Workflow

Goal: keep research PDFs in a known place, catalog them, and open them fast.

## Defaults
- Research root: `~/Documents/Research`
- Catalog output: `~/src/context/index/research_catalog.json`

## Commands
```sh
python -m afs_scawful research catalog
python -m afs_scawful research list
python -m afs_scawful research show 2512-20957v2-XXXXXXXX
python -m afs_scawful research open 2512-20957v2-XXXXXXXX --open
```

## Overrides
- `AFS_RESEARCH_ROOT=/path/to/Research`
- `AFS_RESEARCH_CATALOG=/path/to/research_catalog.json`
- Optional config: `research_paths.toml` in `~/.config/afs/afs_scawful/` or
  `~/.config/afs/plugins/afs_scawful/config/`

Example `research_paths.toml`:
```toml
[paths]
research_root = "~/Documents/Research"
research_catalog = "~/src/context/index/research_catalog.json"
```

## Notes
- Abstract excerpts are auto-extracted from the first pages; verify before quoting.
- `--open` uses the OS default PDF viewer (Preview on macOS).
- For richer metadata extraction, install the optional dependency:
  `pip install -e '.[research]'`
