#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="${HOST:-medical-mechanica}"
WIN_DIR="D:\\afs_training\\scripts"

usage() {
  echo "Usage: $0 [--host HOST] [--win-dir DIR]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --host)
      HOST="$2"
      shift 2
      ;;
    --win-dir)
      WIN_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

WINDOWS_SRC="$SCRIPT_DIR/windows"
if [[ ! -d "$WINDOWS_SRC" ]]; then
  echo "Missing windows helpers at $WINDOWS_SRC"
  exit 1
fi

for file in "$WINDOWS_SRC"/*; do
  [[ -f "$file" ]] || continue
  name="$(basename "$file")"
  b64="$(base64 < "$file" | tr -d '\n')"
  ssh "$HOST" "powershell -NoProfile -Command \"[IO.Directory]::CreateDirectory('${WIN_DIR}'); [IO.File]::WriteAllBytes('${WIN_DIR}\\\\${name}', [Convert]::FromBase64String('${b64}'))\""
  echo "Installed ${name} -> ${WIN_DIR}"
done
