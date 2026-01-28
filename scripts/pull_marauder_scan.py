#!/usr/bin/env python3
"""Pull the latest Momentum Marauder scan log from Flipper over USB."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import serial
import serial.tools.list_ports


LOG_DIR = "/ext/apps_data/marauder/logs"
SCANALL_RE = re.compile(r"scanall_(\d+)\.log")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
RSSI_RE = re.compile(
    r"^>?\s*RSSI:\s*(?P<rssi>-?\d+)\s+Ch:\s*(?P<channel>\d+)\s+"
    r"BSSID:\s*(?P<bssid>[0-9a-fA-F:]{17})\s+ESSID:\s*(?P<essid>.*)$"
)
STA_RE = re.compile(
    r"^(?P<index>\d+):\s+(?P<left>ap|sta):\s*(?P<left_mac>[0-9a-fA-F:]{17})"
    r"\s+->\s+(?P<right>ap|sta):\s*(?P<right_mac>[0-9a-fA-F:]{17})"
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_flipper_port() -> str:
    for port in serial.tools.list_ports.comports():
        if "Flipper" in port.description or "usbmodem" in port.device:
            return port.device
    raise SystemExit("Flipper serial port not found. Check USB connection.")


def _read_cli(ser: serial.Serial, timeout_seconds: float = 3.0) -> str:
    deadline = time.time() + timeout_seconds
    chunks: list[str] = []
    while time.time() < deadline:
        data = ser.read(4096)
        if data:
            chunks.append(data.decode("utf-8", errors="replace"))
            deadline = time.time() + 1.0
        time.sleep(0.02)
    return "".join(chunks)


def cli_command(ser: serial.Serial, command: str, timeout_seconds: float = 3.0) -> str:
    ser.write((command.strip() + "\r\n").encode("utf-8"))
    ser.flush()
    return _read_cli(ser, timeout_seconds=timeout_seconds)


def parse_log_listing(output: str) -> list[tuple[str, int]]:
    files: list[tuple[str, int]] = []
    for line in output.splitlines():
        line = ANSI_RE.sub("", line).strip()
        if not line.startswith("[F]"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        name = parts[1]
        size_raw = parts[2].replace("b", "")
        try:
            size = int(size_raw)
        except ValueError:
            size = 0
        files.append((name, size))
    return files


def select_latest_scanall(files: list[tuple[str, int]]) -> str | None:
    best_index = -1
    best_name = None
    for name, _size in files:
        match = SCANALL_RE.match(name)
        if not match:
            continue
        index = int(match.group(1))
        if index > best_index:
            best_index = index
            best_name = name
    return best_name


def parse_scanall(output: str) -> dict:
    networks = []
    links = []
    notes = []
    in_scan = False
    for raw_line in output.splitlines():
        line = ANSI_RE.sub("", raw_line).strip()
        if not line:
            continue
        if line.startswith("#scanall"):
            in_scan = True
            continue
        if line.startswith("#stopscan"):
            break
        if not in_scan:
            continue
        match = RSSI_RE.match(line)
        if match:
            networks.append(
                {
                    "rssi": int(match.group("rssi")),
                    "channel": int(match.group("channel")),
                    "bssid": match.group("bssid").lower(),
                    "essid": match.group("essid").strip(),
                }
            )
            continue
        match = STA_RE.match(line)
        if match:
            links.append(
                {
                    "left_role": match.group("left"),
                    "left_mac": match.group("left_mac").lower(),
                    "right_role": match.group("right"),
                    "right_mac": match.group("right_mac").lower(),
                }
            )
            continue
        if "RXd WPS Configs" in line or line.startswith("Beacon:"):
            notes.append(line)
            continue
    return {
        "kind": "marauder_scanall",
        "source": "flipper_marauder",
        "captured_at": iso_now(),
        "networks": networks,
        "links": links,
        "notes": notes,
    }


def write_context(context_root: Path, payload: dict) -> None:
    network_dir = context_root / "knowledge" / "network"
    network_dir.mkdir(parents=True, exist_ok=True)
    state_path = network_dir / "state.json"
    events_path = network_dir / "events.jsonl"
    with open(state_path, "w") as f:
        json.dump(payload, f, indent=2)
    with open(events_path, "a") as f:
        f.write(json.dumps(payload) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull latest Marauder scanall log from Flipper.")
    parser.add_argument("--context-root", default=str(Path.home() / ".context"), help="Context root path")
    parser.add_argument("--port", help="Flipper serial port (auto-detect if omitted)")
    parser.add_argument("--log-file", help="Specific scanall log file name")
    parser.add_argument("--debug", action="store_true", help="Print debug info")
    args = parser.parse_args()

    port = args.port or find_flipper_port()
    context_root = Path(args.context_root).expanduser()

    ser = serial.Serial(port, 115200, timeout=0.4)
    try:
        listing = cli_command(ser, f"storage list {LOG_DIR}")
        files = parse_log_listing(listing)
        if args.debug:
            scanall_files = [f for f in files if f[0].startswith("scanall")]
            print(f"Found {len(files)} files, scanall={len(scanall_files)}")
            for name, size in scanall_files[:10]:
                print(f"{name} ({size} bytes)")
        if args.log_file:
            log_name = args.log_file
        else:
            log_name = select_latest_scanall(files)
        if not log_name:
            raise SystemExit("No scanall logs found.")

        log_output = cli_command(ser, f"storage read {LOG_DIR}/{log_name}", timeout_seconds=6.0)
    finally:
        ser.close()

    payload = parse_scanall(log_output)
    write_context(context_root, payload)

    print(
        f"Wrote {len(payload['networks'])} networks and {len(payload['links'])} links "
        f"to {context_root / 'knowledge' / 'network' / 'state.json'}"
    )


if __name__ == "__main__":
    main()
