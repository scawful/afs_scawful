# Label Indexes (z3dk)

## Default index outputs
- `~/src/hobby/z3dk/.context/knowledge/label_index_usdasm.csv`
- `~/src/hobby/z3dk/.context/knowledge/label_index.csv`
- `~/src/hobby/z3dk/.context/knowledge/label_index_all.csv`
- `~/src/hobby/z3dk/.context/knowledge/labels_merged.csv`

## Quick lookups
- Symbol search: `rg -n "^Link_Main," ~/src/hobby/z3dk/.context/knowledge/label_index_usdasm.csv`
- Address search: `rg -n "\$07:8" ~/src/hobby/z3dk/.context/knowledge/label_index_usdasm.csv`

## Regenerate indexes
Run from `~/src/hobby/z3dk` (uses defaults if paths exist):
`python3 scripts/generate_label_indexes.py`

If your usdasm root is elsewhere (ex: gigaleak export):
`python3 scripts/generate_label_indexes.py --usdasm-root ~/src/hobby/alttp-gigaleak/DISASM/usdasm`

Shortcut from Oracle repo (regenerates z3dk indexes and can sync to Mesen2):
`python3 ~/src/hobby/oracle-of-secrets/scripts/mesen2_client.py labels-refresh --sync`
