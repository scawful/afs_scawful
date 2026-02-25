# Command map: mesen2-mcp -> mesen2_client.py

Use the socket CLI as the canonical replacement for MCP tools.

| MCP tool | CLI equivalent | Example |
| --- | --- | --- |
| mesen_status | `state` or `debug-status` | `python3 scripts/mesen2_client.py state` |
| mesen_load_rom | `rom-load` | `python3 scripts/mesen2_client.py rom-load /path/to/rom.sfc` |
| mesen_control | `pause` / `resume` / `reset` | `python3 scripts/mesen2_client.py pause` |
| mesen_run | `run` | `python3 scripts/mesen2_client.py run --frames 60` |
| mesen_save_state | `save` / `smart-save` | `python3 scripts/mesen2_client.py save 1` |
| mesen_load_state | `load` | `python3 scripts/mesen2_client.py load 1` |
| mesen_step | `step` | `python3 scripts/mesen2_client.py step 1 --mode over` |
| mesen_get_pc | `pc` | `python3 scripts/mesen2_client.py pc` |
| mesen_set_pc | `pc <addr>` | `python3 scripts/mesen2_client.py pc 0x008000` |
| mesen_eval | `eval` | `python3 scripts/mesen2_client.py eval "A"` |
| mesen_breakpoint_* | `breakpoint` | `python3 scripts/mesen2_client.py breakpoint --add 0x008000:execute` |
| mesen_read_memory | `mem-read` | `python3 scripts/mesen2_client.py mem-read 0x7E0000 --len 16` |
| mesen_write_memory | `mem-write` | `python3 scripts/mesen2_client.py mem-write 0x7E0000 "A9 00"` |
| mesen_memory_size | `mem-size` | `python3 scripts/mesen2_client.py mem-size --memtype wram` |
| mesen_input | `press` | `python3 scripts/mesen2_client.py press right --frames 5` |
| mesen_screenshot | `screenshot` | `python3 scripts/mesen2_client.py screenshot --out /tmp/shot.png` |
| mesen_diff_states | `state-diff` / `state-compare` | `python3 scripts/mesen2_client.py state-diff` |
| mesen_bridge_registers | `cpu` | `python3 scripts/mesen2_client.py cpu` |
| mesen_bridge_disasm | `disasm` | `python3 scripts/mesen2_client.py disasm 0x008000 --count 10` |
| mesen_bridge_search | `mem-search` | `python3 scripts/mesen2_client.py mem-search --pattern "A9 00"` |
| mesen_bridge_watch | `watch` / `mem-watch` | `python3 scripts/mesen2_client.py watch --profile overworld` |
| mesen_bridge_exec | `lua` | `python3 scripts/mesen2_client.py lua "return 1"` |
| mesen_bridge_load_script | `load-script` | `python3 scripts/mesen2_client.py load-script /path/to/script.lua` |
| mesen_p_watch_* | `p-watch` / `p-log` / `p-assert` | `python3 scripts/mesen2_client.py p-watch start --depth 500` |
| mesen_mem_watch_add | `mem-watch add` | `python3 scripts/mesen2_client.py mem-watch add 0x7E0022` |
| mesen_mem_blame | `mem-blame` | `python3 scripts/mesen2_client.py mem-blame --addr 0x7E0022` |
| mesen_symbols_load | `symbols-load` | `python3 scripts/mesen2_client.py symbols-load /path/to/symbols.json` |
| mesen_symbols_resolve | `symbols` | `python3 scripts/mesen2_client.py symbols Link_Main` |
| mesen_collision_overlay | `collision-overlay` | `python3 scripts/mesen2_client.py collision-overlay --enable` |
| mesen_collision_dump | `collision-dump` | `python3 scripts/mesen2_client.py collision-dump` |
| mesen_trace | `trace` / `trace-run` | `python3 scripts/mesen2_client.py trace --action start` |
| draw_path | `draw-path` | `python3 scripts/mesen2_client.py draw-path 10,10,20,20` |

## Socket-only extras (no MCP equivalent)
- `mem-snapshot <name>` / `mem-diff <name>`
- `labels set|get|lookup|clear`
- `cheat add|list|clear`
- `speed [multiplier]`
- `rewind --seconds N`

Notes:
- The Lua bridge command (`mesen_bridge_command`) is deprecated. Use socket commands instead.
- For bulk calls, use `batch` with a JSON array.
- Socket selection: pass `--socket` / `--instance`, or set `MESEN2_AUTO_ATTACH=1`.
