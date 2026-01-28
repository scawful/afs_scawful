#!/usr/bin/env python3
import argparse
import json
import socket


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a UDP JSON packet to the NERV bridge.")
    parser.add_argument("--host", default="127.0.0.1", help="Destination host")
    parser.add_argument("--port", type=int, default=31337, help="Destination port")
    parser.add_argument("--payload", help="Raw JSON payload string")
    parser.add_argument("--sample", action="store_true", help="Send a sample WiFi scan payload")
    args = parser.parse_args()

    if args.payload:
        payload = args.payload
    elif args.sample:
        payload = json.dumps(
            {
                "kind": "wifi_scan",
                "networks": [
                    {"ssid": "NERV-LAB", "rssi": -45, "channel": 11},
                    {"ssid": "guest", "rssi": -70, "channel": 1},
                ],
                "source": "esp32",
            }
        )
    else:
        raise SystemExit("Provide --payload or --sample.")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(payload.encode("utf-8"), (args.host, args.port))
    finally:
        sock.close()

    print(f"Sent UDP payload to {args.host}:{args.port}")


if __name__ == "__main__":
    main()
