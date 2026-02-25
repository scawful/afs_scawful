# Troubleshooting

- **Socket not found**: confirm Mesen2 OOS is running and the ROM is loaded. Look for `/tmp/mesen2-*.sock` or set `MESEN2_AUTO_ATTACH=1`.
- **Wrong socket**: set `MESEN2_SOCKET_PATH=/tmp/mesen2-<pid>.sock` or pass `--socket`. If registry is enabled, use `--instance` or `MESEN2_INSTANCE`.
- **Stale sockets**: `python3 scripts/mesen2_client.py socket-cleanup`.
- **ROM load screen**: run `python3 scripts/mesen2_client.py rom-load /path/to/rom.sfc`.
- **Debugger not available**: open the ROM in Mesen2 OOS and ensure the debugger is enabled.
- **Symbols missing**: rebuild ROM to refresh `Roms/oos168x.mlb`, then run `python3 scripts/export_symbols.py --sync` (preferred) or `python3 scripts/mesen2_client.py labels-sync` (vanilla-only).
- **Label indexes stale**: `python3 scripts/mesen2_client.py labels-refresh --sync` (regenerates z3dk indexes + syncs USDASM labels).
- **Socket diagnostics**: use `capabilities`, `metrics`, and `command-history --count 50` to confirm feature flags and recent errors.
- **Lua fails**: prefer socket commands; `lua` is best-effort for quick probes.
