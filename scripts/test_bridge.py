#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from afs_scawful.integrations.hardware_bridge import HardwareBridge

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    parser = argparse.ArgumentParser(description="NERV Hardware Bridge test runner")
    parser.add_argument("--context-root", default="./.context_mock", help="Context root path")
    parser.add_argument("--udp-host", default=None, help="ESP32 UDP listen host")
    parser.add_argument("--udp-port", type=int, default=None, help="ESP32 UDP listen port")
    parser.add_argument("--forward-host", default=None, help="Forward UDP host")
    parser.add_argument("--forward-port", type=int, default=None, help="Forward UDP port")
    parser.add_argument(
        "--forward-target",
        action="append",
        default=[],
        help="Forward target in host:port form (repeatable)",
    )
    parser.add_argument(
        "--forward-mode",
        default=None,
        choices=["none", "udp"],
        help="Forward mode for ESP32 packets",
    )
    parser.add_argument("--no-serial", action="store_true", help="Disable Flipper serial monitor")
    parser.add_argument("--no-network", action="store_true", help="Disable ESP32 UDP monitor")
    args = parser.parse_args()

    context_root = Path(args.context_root)
    context_root.mkdir(exist_ok=True)
    
    forward_targets = []
    for raw in args.forward_target:
        if ":" not in raw:
            raise SystemExit(f"Invalid --forward-target '{raw}' (expected host:port)")
        host, port_str = raw.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError as exc:
            raise SystemExit(f"Invalid --forward-target '{raw}' (bad port)") from exc
        forward_targets.append((host, port))

    bridge = HardwareBridge(
        context_root,
        esp32_udp_host=args.udp_host,
        esp32_udp_port=args.udp_port,
        forward_targets=forward_targets or None,
        forward_host=args.forward_host,
        forward_port=args.forward_port,
        forward_mode=args.forward_mode,
        enable_serial=not args.no_serial,
        enable_network=not args.no_network,
    )
    
    print(">>> Starting NERV Hardware Bridge Test")
    if not args.no_serial:
        print(">>> Please ensure Flipper Zero is connected via USB")
    if not args.no_network:
        print(">>> ESP32 UDP listener enabled")
        if args.forward_mode == "udp":
            if forward_targets:
                print(f">>> UDP forward enabled ({len(forward_targets)} targets)")
            else:
                print(">>> UDP forward enabled")
    print(">>> Press Ctrl+C to stop")
    
    try:
        await bridge.start()
        # Keep running to allow monitoring
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n>>> Stopping...")
        await bridge.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
