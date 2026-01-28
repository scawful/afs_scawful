"""
NERV Hardware Bridge
Connects physical devices (Flipper, Arduino) to the AFS context.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HardwareBridge:
    def __init__(
        self,
        context_root: Path,
        esp32_udp_host: str | None = None,
        esp32_udp_port: int | None = None,
        forward_targets: list[tuple[str, int]] | None = None,
        forward_host: str | None = None,
        forward_port: int | None = None,
        forward_mode: str | None = None,
        enable_serial: bool = True,
        enable_network: bool = True,
    ):
        self.context_root = context_root
        self.running = False
        self.flipper_connected = False
        self.network_state_path = context_root / "knowledge/network/state.json"
        self.network_events_path = context_root / "knowledge/network/events.jsonl"
        self.enable_serial = enable_serial
        self.enable_network = enable_network
        self.esp32_udp_host = esp32_udp_host or os.environ.get("NERV_ESP32_HOST", "0.0.0.0")
        self.esp32_udp_port = self._resolve_udp_port(esp32_udp_port)
        self.forward_host = forward_host or os.environ.get("NERV_FORWARD_HOST", "")
        self.forward_port = self._resolve_forward_port(forward_port)
        self.forward_mode = (forward_mode or os.environ.get("NERV_FORWARD_MODE") or "none").lower()
        self.forward_targets = self._resolve_forward_targets(
            forward_targets,
            self.forward_host,
            self.forward_port,
        )
        self._forward_transports: list[asyncio.DatagramTransport] = []
        self._udp_transport: asyncio.DatagramTransport | None = None
        self._udp_protocol: asyncio.DatagramProtocol | None = None

    @staticmethod
    def _resolve_udp_port(override: int | None) -> int:
        if override is not None:
            return int(override)
        env_port = os.environ.get("NERV_ESP32_PORT")
        if env_port:
            try:
                return int(env_port)
            except ValueError:
                logger.warning("Invalid NERV_ESP32_PORT=%s; using default.", env_port)
        return 31337

    @staticmethod
    def _resolve_forward_port(override: int | None) -> int:
        if override is not None:
            return int(override)
        env_port = os.environ.get("NERV_FORWARD_PORT")
        if env_port:
            try:
                return int(env_port)
            except ValueError:
                logger.warning("Invalid NERV_FORWARD_PORT=%s; disabling forward.", env_port)
        return 0

    @staticmethod
    def _resolve_forward_targets(
        override_targets: list[tuple[str, int]] | None,
        forward_host: str,
        forward_port: int,
    ) -> list[tuple[str, int]]:
        if override_targets:
            return list(override_targets)

        env_targets = os.environ.get("NERV_FORWARD_TARGETS", "").strip()
        targets: list[tuple[str, int]] = []
        if env_targets:
            for raw in env_targets.split(","):
                raw = raw.strip()
                if not raw:
                    continue
                if ":" not in raw:
                    logger.warning("Invalid NERV_FORWARD_TARGETS entry: %s", raw)
                    continue
                host, port_str = raw.rsplit(":", 1)
                try:
                    port = int(port_str)
                except ValueError:
                    logger.warning("Invalid forward port in NERV_FORWARD_TARGETS: %s", raw)
                    continue
                targets.append((host.strip(), port))

        if not targets and forward_host and forward_port:
            targets.append((forward_host, forward_port))

        return targets
        
    async def start(self):
        """Start the bridge service."""
        self.running = True
        logger.info("NERV Hardware Bridge started")
        tasks = []
        if self.enable_serial:
            tasks.append(self._monitor_serial())
        if self.enable_network:
            tasks.append(self._monitor_network_packets())
        if not tasks:
            logger.warning("No hardware bridge monitors enabled.")
            return
        await asyncio.gather(*tasks)
        
    async def stop(self):
        self.running = False
        logger.info("NERV Hardware Bridge stopped")
        if self._udp_transport:
            self._udp_transport.close()
        for transport in self._forward_transports:
            transport.close()
        self._forward_transports = []
        
    async def _monitor_serial(self):
        """Watch for Flipper Zero serial connection."""
        try:
            import serial
            import serial.tools.list_ports
        except ModuleNotFoundError:
            logger.warning("pyserial not installed; skipping serial monitor.")
            return
        
        logger.info("Starting serial monitor...")
        while self.running:
            ports = list(serial.tools.list_ports.comports())
            flipper_port = None
            
            for port in ports:
                if "Flipper" in port.description or "usbmodem" in port.device:
                    flipper_port = port.device
                    break
            
            if flipper_port and not self.flipper_connected:
                logger.info(f"Flipper Zero detected at {flipper_port}")
                self.flipper_connected = True
                try:
                    self.ser = serial.Serial(flipper_port, 115200, timeout=1)
                    await self.send_wisdom("The flow of time is always cruel...")
                except Exception as e:
                    logger.error(f"Failed to open serial: {e}")
                    self.flipper_connected = False
            elif not flipper_port and self.flipper_connected:
                logger.info("Flipper Zero disconnected")
                self.flipper_connected = False
                if hasattr(self, 'ser'):
                    self.ser.close()
                
            await asyncio.sleep(2)

    async def send_wisdom(self, message: str):
        """Send a message to the Flipper's serial console."""
        if self.flipper_connected and hasattr(self, 'ser'):
            logger.info(f"Sending wisdom to Flipper: {message}")
            # Flipper CLI usually expects commands or just raw text
            # We'll send it as a notification if possible, or just raw print
            self.ser.write(f"\r\nNERV: {message}\r\n".encode())
            self.ser.flush()
            
    async def _monitor_network_packets(self):
        """Listen for UDP/MQTT packets from ESP32s."""
        loop = asyncio.get_running_loop()

        class _ESP32Protocol(asyncio.DatagramProtocol):
            def __init__(self, handler):
                self.handler = handler

            def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
                self.handler(data, addr)

            def error_received(self, exc: Exception) -> None:
                logger.warning("ESP32 UDP error: %s", exc)

        logger.info(
            "Listening for ESP32 UDP on %s:%s",
            self.esp32_udp_host,
            self.esp32_udp_port,
        )
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _ESP32Protocol(self._handle_esp32_packet),
            local_addr=(self.esp32_udp_host, self.esp32_udp_port),
        )
        self._udp_transport = transport
        self._udp_protocol = protocol
        await self._setup_forward_transport()

        try:
            while self.running:
                await asyncio.sleep(1)
        finally:
            transport.close()
            self._udp_transport = None
            self._udp_protocol = None
            for transport in self._forward_transports:
                transport.close()
            self._forward_transports = []

    async def _setup_forward_transport(self) -> None:
        if self.forward_mode != "udp":
            return
        if not self.forward_targets:
            logger.warning("Forward mode enabled but host/port missing; skipping.")
            return
        loop = asyncio.get_running_loop()
        for host, port in self.forward_targets:
            transport, _protocol = await loop.create_datagram_endpoint(
                asyncio.DatagramProtocol,
                remote_addr=(host, port),
            )
            self._forward_transports.append(transport)
            logger.info("Forwarding ESP32 UDP to %s:%s", host, port)

    def _handle_esp32_packet(self, data: bytes, addr: Tuple[str, int]) -> None:
        self._forward_packet(data)
        text = data.decode("utf-8", errors="replace").strip()
        if not text:
            return
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            self._append_network_event(
                {
                    "received_at": _iso_now(),
                    "source": "esp32_udp",
                    "addr": {"host": addr[0], "port": addr[1]},
                    "raw": text,
                    "error": "invalid_json",
                }
            )
            logger.warning("Invalid JSON from ESP32 (%s): %s", addr, text[:200])
            return

        event = {
            "received_at": _iso_now(),
            "source": "esp32_udp",
            "addr": {"host": addr[0], "port": addr[1]},
            "payload": payload,
        }
        self._append_network_event(event)

        if isinstance(payload, dict):
            kind = str(payload.get("kind", "")).lower()
            if kind in {"wifi_scan", "marauder_scan", "marauder"}:
                self.update_network_map(payload)
                return
            if any(key in payload for key in ("networks", "aps", "access_points")):
                self.update_network_map(payload)
                return

    def _forward_packet(self, data: bytes) -> None:
        if not self._forward_transports:
            return
        for transport in list(self._forward_transports):
            try:
                transport.sendto(data)
            except Exception as exc:
                logger.warning("Failed to forward UDP packet: %s", exc)

    def _append_network_event(self, event: Dict[str, Any]) -> None:
        self.network_events_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.network_events_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def log_plant_sensor(self, sensor_id: str, data: dict):
        """Log sensor data to context."""
        sensor_path = self.context_root / "knowledge/sensors" / f"{sensor_id}.jsonl"
        sensor_path.parent.mkdir(parents=True, exist_ok=True)
        with open(sensor_path, "a") as f:
            f.write(json.dumps(data) + "\n")

    def update_network_map(self, marauder_data: Dict):
        """Update the knowledge graph with WiFi scan data."""
        self.network_state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.network_state_path, "w") as f:
            payload = dict(marauder_data)
            payload.setdefault("received_at", _iso_now())
            json.dump(payload, f, indent=2)
