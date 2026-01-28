# NERV Hardware Bridge (Flipper + ESP32)

Status: Draft

## Overview

The hardware bridge listens for ESP32 UDP events and (optionally) Flipper Zero
serial connections, then writes results into the local `.context` knowledge
tree.

Notes:
- Momentum Marauder output format is **Unknown / needs verification**.
- This bridge currently expects ESP32 UDP JSON. Non-JSON payloads are logged as
  raw events.

## Local Smoke Test

```bash
python3 scripts/test_bridge.py --no-serial --udp-host 127.0.0.1 --udp-port 31337
python3 scripts/send_esp32_udp.py --host 127.0.0.1 --port 31337 --sample
```

Artifacts:
- `.context/knowledge/network/state.json`
- `.context/knowledge/network/events.jsonl`

## Remote Relay (Recommended)

ESP32 devices cannot join Tailscale, so run a relay on the home LAN and forward
events to a remote NERV node over Tailscale.

Relay host (home LAN):
```bash
python3 scripts/test_bridge.py \
  --context-root ~/.context \
  --udp-host 0.0.0.0 \
  --udp-port 31337 \
  --forward-mode udp \
  --forward-target mac:31338 \
  --forward-target halext-nj:31338 \
  --no-serial
```

Remote host (NERV node):
```bash
python3 scripts/test_bridge.py \
  --context-root ~/.context \
  --udp-host 0.0.0.0 \
  --udp-port 31338 \
  --no-serial
```

Environment alternative:
```bash
export NERV_FORWARD_MODE=udp
export NERV_FORWARD_TARGETS="mac:31338,halext-nj:31338"
```

## Momentum Marauder Notes

Provide a sample payload from the ESP32 module (or Flipper serial output) so we
can add a schema-specific parser. Until then, the bridge logs raw JSON/text
packets and updates `state.json` when it sees a `kind` of `wifi_scan` or a
payload with `networks`, `aps`, or `access_points`.

## Pull Logs Over USB (No On-Device Typing)

If Marauder is saving scan logs to the SD card, you can pull the latest
`scanall_*.log` file over USB and parse it locally:

```bash
/Users/scawful/src/lab/afs-scawful/.venv/bin/python \
  /Users/scawful/src/lab/afs-scawful/scripts/pull_marauder_scan.py \
  --context-root ~/.context
```

This writes a parsed summary to:
`~/.context/knowledge/network/state.json`
