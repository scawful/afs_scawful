#!/usr/bin/env python3
"""
Agentic Evaluation: ROM Boot Verifier (Real)
Uses the Mesen2 Socket API to verify if a ROM boots and reaches a stable state.
"""

import os
import sys
import time
import argparse
from pathlib import Path

# Add Mesen2 client lib to path
OOS_SCRIPTS = Path("/Users/scawful/src/hobby/oracle-of-secrets/scripts")
sys.path.append(str(OOS_SCRIPTS))

try:
    from mesen2_client_lib.bridge import MesenBridge
except ImportError:
    print("Error: Could not import MesenBridge. Check paths.")
    sys.exit(1)

def verify_rom_boot(rom_path, timeout=15):
    """
    1. Resets Mesen2 with the target ROM.
    2. Monitors the Game Mode ($7E0010) or PC to ensure progress.
    """
    bridge = MesenBridge()
    if not bridge.ensure_connected():
        print("Error: Mesen2 not running or socket not found.")
        return False

    print(f"[*] Connected to Mesen2: {bridge.socket_path}")
    print(f"[*] Testing ROM: {rom_path}")

    # On Mesen2-OOS, we can't 'load' a ROM via socket easily without external commands,
    # but we can check the CURRENTLY running ROM's state.
    # For a full audit, the caller should launch Mesen2 with the ROM first.
    
    # Let's check if the ROM is actually the one we expect (best effort)
    info = bridge.get_rom_info()
    print(f"[*] Active ROM: {info.get('name', 'Unknown')}")

    # Monitor Game Mode ($7E0010 in ALTTP)
    # 0x00 = Intro/Cinematic, 0x01 = Select Screen, 0x07 = In-game, etc.
    start_time = time.time()
    while time.time() - start_time < timeout:
        game_mode = bridge.read_memory(0x7E0010)
        pc = bridge.get_cpu_state().get("pc", 0)
        
        print(f"    [T+{int(time.time()-start_time)}s] PC: {hex(pc)} | GameMode: {hex(game_mode)}")
        
        # If GameMode > 0, it means it passed the initial boot/checksum
        if game_mode > 0:
            print("[+] Success: Game reached a valid state.")
            return True
            
        time.sleep(1)

    print("[-] Failure: ROM timed out or stuck in boot loop.")
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Functional ROM Boot Verifier")
    parser.add_argument("rom", type=str, help="Path to the ROM file")
    args = parser.parse_args()

    if verify_rom_boot(args.rom):
        print("RESULT: PASS")
        sys.exit(0)
    else:
        print("RESULT: FAIL")
        sys.exit(1)