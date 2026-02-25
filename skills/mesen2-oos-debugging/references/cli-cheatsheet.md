# Mesen2-OOS CLI Cheatsheet

## Socket selection
- `--socket /tmp/mesen2-<id>.sock`
- `--instance <name>`
- `MESEN2_AUTO_ATTACH=1` (auto-select newest socket)

## Health and status
- `health`, `debug-status`, `debug-context`, `diagnostics`, `rom-info`
- `capabilities`, `metrics`, `command-history --count 20`
- `agent-register --id <agent> [--name <name>] [--version <ver>]`
- `rom-load <rom.sfc> [--patch <file>]` (load ROM when Mesen2 is on the load screen)

## Run control
- `pause`, `resume`, `reset`
- `run --frames N` or `run --seconds S`
- `step [count] --mode instruction|into|over|out|cycle|ppu|scanline|frame|nmi|irq|back`
- `speed [multiplier]` (get FPS or set speed)
- `rewind --seconds N`

## CPU + state
- `state`, `run-state`, `cpu`, `pc [address]`
- `disasm <address|label> --count N`
- `eval "<expr>" --cpu snes`

## Memory
- `mem-read <addr> --len N --memtype wram`
- `mem-write <addr> "AA BB CC" --memtype wram`
- `mem-search --value <hex> --size N --memtype wram`
- `mem-search --pattern "A9 00 8D" --memtype wram`
- `mem-size --memtype wram`
- `mem-snapshot <name> --memtype WRAM`
- `mem-diff <name>`

## Breakpoints + trace
- `breakpoint --add <addr:type> [--profile <name>]`
- `breakpoint --list | --remove <id> | --clear`
- `trace --action start|stop|status|clear --labels true`
- `trace-run --frames N --count N --output <path.jsonl>`

## Watches + blame
- `profiles` (list watch profiles)
- `watch --profile <name>`
- `mem-watch add <addr> --size N --depth N`
- `mem-watch list | remove <id> | clear`
- `mem-blame --addr <addr>`
- `p-watch start|stop|status`
- `p-log --count N`

## Saves + repro
- `save <slot>` / `load <slot>` / `smart-save <slot>`
- `savestate-label get|set|clear <slot> --label "..."`
- `library`, `lib-save "<label>"`, `lib-load <id>`, `lib-verify <id>`, `lib-verify-all`
- `repro <state_id> --trace --watch <profile>`
- `state-diff` (changes since last call)
- `state-compare --slot-a N --slot-b N`

## Overlays + capture
- `screenshot --out <path.png>`
- `collision-overlay --enable` / `--disable`
- `collision-dump --colmap A` (redirect to file if needed)
- `draw-path "x1,y1,x2,y2" --color #00FF00 --frames 120`

## Symbols + Lua
- `labels-refresh [--sync] [--clear]` (regenerate z3dk indexes; optional sync)
- `labels-sync [--clear]` (vanilla USDASM labels)
- `labels set|get|lookup|clear ...`
- `symbols <query>`
- `symbols-load <path.json> [--clear]`
- `lua "<code>"` or `load-script <path.lua>`

## Cheats + utility
- `cheat add <code> [--format ProActionReplay]`
- `cheat list`
- `cheat clear`
