#!/bin/bash
# Pull latest Veran eval outputs/logs from the Windows host and print summaries.

set -euo pipefail

HOST="${HOST:-medical-mechanica}"
DEST_DIR="${DEST_DIR:-$HOME/src/lab/afs-scawful/docs/eval/veran_v1}"
REMOTE_EVAL_DIR="${REMOTE_EVAL_DIR:-D:\afs_training\evals\veran_v1}"
REMOTE_LOG_DIR="${REMOTE_LOG_DIR:-D:\afs_training\logs}"

usage() {
  cat <<USAGE
Usage: $0 [options]

Options:
  --host HOST               Windows SSH host (default: medical-mechanica)
  --dest-dir PATH           Local destination directory
  --remote-eval-dir PATH    Remote eval directory (Windows path)
  --remote-log-dir PATH     Remote log directory (Windows path)
  -h, --help                Show this help
USAGE
}

to_scp_path() {
  local win_path="$1"
  local unix_path
  unix_path="${win_path//\\//}"
  if [[ "$unix_path" == D:/* ]]; then
    printf '/D:/%s' "${unix_path#D:/}"
    return
  fi
  if [[ "$unix_path" == D:* ]]; then
    printf '/D:/%s' "${unix_path#D:}"
    return
  fi
  printf '%s' "$unix_path"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --dest-dir)
      DEST_DIR="$2"
      shift 2
      ;;
    --remote-eval-dir)
      REMOTE_EVAL_DIR="$2"
      shift 2
      ;;
    --remote-log-dir)
      REMOTE_LOG_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

mkdir -p "$DEST_DIR"

echo "[*] Host: $HOST"
echo "[*] Destination: $DEST_DIR"

latest_quick=$(ssh "$HOST" "powershell -NoProfile -Command \"Get-ChildItem '$REMOTE_EVAL_DIR' -File -Filter 'results_quick_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty Name\"" | tr -d '\r')
latest_holdout=$(ssh "$HOST" "powershell -NoProfile -Command \"Get-ChildItem '$REMOTE_EVAL_DIR' -File -Filter 'results_holdout_*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty Name\"" | tr -d '\r')
latest_log=$(ssh "$HOST" "powershell -NoProfile -Command \"Get-ChildItem '$REMOTE_LOG_DIR' -File -Filter 'veran_v1_eval_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty Name\"" | tr -d '\r')

if [[ -z "$latest_quick" || -z "$latest_holdout" ]]; then
  echo "No eval result files found on $HOST:$REMOTE_EVAL_DIR" >&2
  exit 1
fi

remote_eval_unix=$(to_scp_path "$REMOTE_EVAL_DIR")
remote_log_unix=$(to_scp_path "$REMOTE_LOG_DIR")

echo "[*] Latest quick: $latest_quick"
echo "[*] Latest holdout: $latest_holdout"
[[ -n "$latest_log" ]] && echo "[*] Latest log: $latest_log"

scp "$HOST:${remote_eval_unix}/${latest_quick}" "$DEST_DIR/"
scp "$HOST:${remote_eval_unix}/${latest_holdout}" "$DEST_DIR/"
if [[ -n "$latest_log" ]]; then
  scp "$HOST:${remote_log_unix}/${latest_log}" "$DEST_DIR/" || true
fi

python3 - <<PY
import json
from pathlib import Path

dest = Path(r"$DEST_DIR")
files = [dest / "$latest_quick", dest / "$latest_holdout"]
for p in files:
    data = json.loads(p.read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    print(f"{p.name}: {summary}")
PY

echo "[*] Pull complete."
