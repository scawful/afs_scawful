# ALTTP Disassembly Paths

## Primary sources
- US disassembly (preferred for tooling parity): `~/src/hobby/alttp-gigaleak/DISASM/usdasm`
- JP disassembly (fallback when US export is missing): `~/src/hobby/alttp-gigaleak/DISASM/jpdasm`

## Alternate copies (use only if the primary path is unavailable)
- `~/src/hobby/usdasm`
- `~/src/workspaces/usdasm`

## Search patterns
- `rg -n "Link_Main" <usdasm_path>`
- `rg -n "Sprite_" <usdasm_path>`
- `rg -n "bank_07" <usdasm_path>`

## Notes
- Treat usdasm/jpdasm as read-only references.
- Keep the disassembly root you search aligned with the label index you consult.
