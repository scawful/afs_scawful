#!/bin/bash
set -euo pipefail

HOST="${HOST:-medical-mechanica}"
WIN_DIR="${WIN_DIR:-D:\\afs_training\\scripts}"
DISTRO="${DISTRO:-Ubuntu}"
SRC_ROOT="${SRC_ROOT:-D:\\src}"
TRAINING_ROOT="${TRAINING_ROOT:-D:\\src\\training}"
MEMORY=""
PROCESSORS=""
SWAP="${SWAP:-16GB}"
FORCE=false
SKIP_PACKAGE_INSTALL=false

usage() {
  cat <<'USAGE'
Usage: windows_setup_wsl.sh [options]

Options:
  --host HOST             SSH host (default: medical-mechanica)
  --win-dir DIR           Windows helper directory (default: D:\afs_training\scripts)
  --distro NAME           WSL distro name (default: Ubuntu)
  --src-root PATH         Windows src root (default: D:\src)
  --training-root PATH    Windows training root (default: D:\src\training)
  --memory SIZE           Write memory=SIZE to .wslconfig
  --processors N          Write processors=N to .wslconfig
  --swap SIZE             Write swap=SIZE to .wslconfig (default: 16GB)
  --skip-package-install  Skip apt package install in WSL
  --force                 Overwrite managed config files
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --win-dir)
      WIN_DIR="$2"
      shift 2
      ;;
    --distro)
      DISTRO="$2"
      shift 2
      ;;
    --src-root)
      SRC_ROOT="$2"
      shift 2
      ;;
    --training-root)
      TRAINING_ROOT="$2"
      shift 2
      ;;
    --memory)
      MEMORY="$2"
      shift 2
      ;;
    --processors)
      PROCESSORS="$2"
      shift 2
      ;;
    --swap)
      SWAP="$2"
      shift 2
      ;;
    --skip-package-install)
      SKIP_PACKAGE_INSTALL=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

args=(
  "-Distro" "$DISTRO"
  "-SrcRoot" "$SRC_ROOT"
  "-TrainingRoot" "$TRAINING_ROOT"
  "-Swap" "$SWAP"
)

if [[ -n "$MEMORY" ]]; then
  args+=("-Memory" "$MEMORY")
fi

if [[ -n "$PROCESSORS" ]]; then
  args+=("-Processors" "$PROCESSORS")
fi

if $SKIP_PACKAGE_INSTALL; then
  args+=("-SkipPackageInstall")
fi

if $FORCE; then
  args+=("-Force")
fi

quoted_args=()
for arg in "${args[@]}"; do
  quoted_args+=("\"${arg}\"")
done

ssh "$HOST" "powershell -NoProfile -File ${WIN_DIR}\\\\afs_setup_wsl.ps1 ${quoted_args[*]}"
