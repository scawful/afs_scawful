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
- `AFS_RESEARCH_OVERRIDES=/path/to/research_overrides.json`
- Optional config: `research_paths.toml` in `~/.config/afs/afs_scawful/` or
  `~/.config/afs/plugins/afs_scawful/config/`
- Optional overrides: `research_overrides.json` in the same config directories.

Example `research_paths.toml`:
```toml
[paths]
research_root = "~/Documents/Research"
research_catalog = "~/src/context/index/research_catalog.json"
```

Example `research_overrides.json`:
```json
{
  "papers": {
    "2510.04950v1.pdf": {
      "title": "Unknown / needs verification",
      "author": "Unknown / needs verification"
    },
    "7799_Quantifying_Human_AI_Syne.pdf": {
      "title": "Unknown / needs verification",
      "author": "Unknown / needs verification"
    }
  }
}
```

## Notes
- Abstract excerpts are auto-extracted from the first pages; verify before quoting.
- `--open` uses the OS default PDF viewer (Preview on macOS).
- For richer metadata extraction, install the optional dependency:
  `pip install -e '.[research]'`
