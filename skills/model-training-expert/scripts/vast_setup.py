#!/usr/bin/env python3
"""
vast_setup.py - Provision and configure Vast.ai instances for AI training.
(2026 Edition)
"""

import sys
import json
import subprocess

def check_vast_cli():
    try:
        subprocess.run(["vast", "--version"], capture_output=True, check=True)
        return True
    except:
        return False

def main():
    if not check_vast_cli():
        print("Error: 'vast' CLI not found. Please install it: pip install vastai")
        sys.exit(1)

    # Simplified example of provisioning an RTX 4090
    print("Searching for available RTX 4090 instances...")
    # vast search offers 'gpu_name == RTX_4090  rentable == True'
    
    print("Recommended instances found. Use 'vast rent instance <id>' to begin.")
    print("Once rented, use 'scripts/configure_env.sh' to install PyTorch/MLX/PEFT.")

if __name__ == "__main__":
    main()
