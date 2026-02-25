# Lookup Patterns

## Hyrule Historian (preferred)
- Address or label: `mcp__hyrule-historian__lookup("$07:8000")` or `mcp__hyrule-historian__lookup("Link_Main")`
- Text search: `mcp__hyrule-historian__search("Link_HandleYItem", scope="vanilla")`
- RAM/ROM references: `mcp__hyrule-historian__consult_reference(topic="memory")`
- Refresh stale indexes: `mcp__hyrule-historian__management(action="reload")`

## Fallback search (raw files)
- `rg -n "Link_HandleYItem" ~/src/hobby/alttp-gigaleak/DISASM/usdasm`
- `rg -n "#_078" ~/src/hobby/alttp-gigaleak/DISASM/usdasm`

## Interpretation tips
- Prefer US usdasm for parity with Mesen2 addresses and label indexes.
- Use label_index_usdasm.csv when Hyrule Historian is out of date or missing symbols.
